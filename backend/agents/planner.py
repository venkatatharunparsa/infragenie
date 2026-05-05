"""
Planner Agent
-------------
The PlannerAgent translates a decomposed infrastructure intent into a concrete,
ordered Terraform execution plan. It consults the RAG knowledge base (AWS best
practices and Terraform patterns) to select the most appropriate IaC modules,
generates HCL via Gemini, and validates it.
"""

import asyncio
import logging
import os
import re
import tempfile
from datetime import datetime

import google.generativeai as genai

from .models import AgentResult

logger = logging.getLogger(__name__)

class PlannerAgent:
    """
    Produces a Terraform plan from a structured infrastructure intent.

    The planner translates plain English user requests into valid Terraform HCL code.
    It retrieves context from a RAG knowledge base, uses Gemini to generate the code,
    validates the syntax via the Terraform CLI, and estimates complexity.
    """

    def __init__(self, config, rag_client=None):
        """
        Initialize the PlannerAgent.

        Parameters
        ----------
        config : Settings
            Application configuration containing API keys and budget thresholds.
        rag_client : Any, optional
            RAG client for retrieving context.
        """
        self.config = config
        self.rag_client = rag_client
        self.name = "planner"
        
        # Initialize Gemini model using google-generativeai
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-1.5-pro")

    async def run(self, input: dict) -> AgentResult:
        """
        Generate a Terraform plan for the given user request.

        Parameters
        ----------
        input : dict
            Contains the user's request text under 'request' or 'intent'.

        Returns
        -------
        AgentResult
            Contains the proposed HCL Terraform snippet and validation status.
        """
        user_request = input.get("request", input.get("intent", ""))
        
        rag_context = await self._retrieve_context(user_request)
        tf_code = await self._generate_tf(user_request, rag_context)
        is_valid, error_message = await self._validate_syntax(tf_code)
        
        resource_types = await self._extract_resource_types(tf_code)
        complexity = await self._estimate_complexity(tf_code)
        
        if not is_valid:
            logger.warning("[PlannerAgent] Generated Terraform code has syntax errors.")
            return AgentResult(
                agent=self.name,
                severity="high",
                finding=f"Generated Terraform code has syntax errors: {error_message}",
                recommended_action="Review and correct the generated Terraform code manually.",
                requires_human=True,
                proposed_tf=tf_code,
                timestamp=datetime.utcnow(),
                metadata={
                    "valid": False, 
                    "error": error_message, 
                    "complexity": complexity, 
                    "resources": resource_types
                }
            )

        logger.info("[PlannerAgent] Successfully generated valid %s Terraform plan.", complexity)
        return AgentResult(
            agent=self.name,
            severity="info",
            finding=f"Generated {complexity} Terraform plan with {len(resource_types)} unique resource types.",
            recommended_action="Review the proposed Terraform plan and approve for execution.",
            requires_human=True,
            proposed_tf=tf_code,
            timestamp=datetime.utcnow(),
            metadata={
                "valid": True, 
                "complexity": complexity, 
                "resources": resource_types
            }
        )

    async def _retrieve_context(self, user_request: str) -> str:
        """
        Retrieves top 5 similar past deployments and patterns from the RAG knowledge base.
        """
        try:
            from rag.chroma_client import get_or_create_collection
            from rag.embedder import embed_text
            
            # If rag_client is None, fallback to direct ChromaDB access
            collection = None
            if self.rag_client and hasattr(self.rag_client, "get_or_create_collection"):
                collection = self.rag_client.get_or_create_collection("terraform_patterns")
            
            if not collection:
                collection = get_or_create_collection("terraform_patterns", self.config.CHROMA_PERSIST_DIR)
                
            query_embedding = embed_text(user_request, task_type="retrieval_query")
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=5
            )
            
            if results and results.get("documents") and results["documents"] and results["documents"][0]:
                return "\n\n".join(results["documents"][0])
            return "No relevant past deployments found."
        except Exception as exc:
            logger.warning("[PlannerAgent] Failed to retrieve context: %s", exc)
            return "Failed to retrieve context."

    async def _generate_tf(self, user_request: str, rag_context: str) -> str:
        """
        Generates Terraform HCL code using the Gemini API based on user request and RAG context.
        """
        prompt = f"""You are a Terraform expert. Generate valid AWS Terraform HCL code.
Rules:
- Always include provider aws block with region variable
- Always add tags to every resource: {{Project=InfraGenie, ManagedBy=AI}}
- Always include description in security groups
- Never use 0.0.0.0/0 in ingress rules
- Always enable versioning on S3 buckets
- Always enable encryption on RDS instances
- Output ONLY valid HCL code, no explanation, no markdown fences

Context from past deployments:
{rag_context}

User request: {user_request}

Generate complete Terraform code:"""

        try:
            logger.debug("[PlannerAgent] Calling Gemini to generate Terraform code.")
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            raw = response.text.strip()
            
            # Clean up potential markdown formatting
            if raw.startswith("```"):
                lines = raw.splitlines()
                if len(lines) > 1:
                    raw = "\n".join(lines[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
            return raw.strip()
        except Exception as exc:
            logger.error("[PlannerAgent] Error generating TF code: %s", exc)
            return ""

    async def _validate_syntax(self, tf_code: str) -> tuple[bool, str]:
        """
        Runs 'terraform validate' via subprocess on the generated code in a temp directory.
        """
        if not tf_code:
            return False, "No Terraform code was generated."

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                main_tf_path = os.path.join(temp_dir, "main.tf")
                with open(main_tf_path, "w", encoding="utf-8") as f:
                    f.write(tf_code)
                    
                # Initialize Terraform in the temp directory (without backend)
                init_proc = await asyncio.create_subprocess_exec(
                    "terraform", "init", "-backend=false",
                    cwd=temp_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await init_proc.communicate()
                
                # Validate Terraform syntax
                val_proc = await asyncio.create_subprocess_exec(
                    "terraform", "validate", "-no-color",
                    cwd=temp_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await val_proc.communicate()
                
                if val_proc.returncode == 0:
                    return True, ""
                else:
                    err_msg = stderr.decode("utf-8").strip()
                    if not err_msg:
                        err_msg = stdout.decode("utf-8").strip()
                    return False, err_msg
        except FileNotFoundError:
            logger.warning("[PlannerAgent] Terraform CLI not found, skipping validation.")
            return False, "Terraform CLI not found on the system."
        except Exception as exc:
            logger.error("[PlannerAgent] Error during syntax validation: %s", exc)
            return False, str(exc)

    async def _extract_resource_types(self, tf_code: str) -> list[str]:
        """
        Parse the HCL string and extract all resource type names.
        """
        matches = re.findall(r'resource\s+"([^"]+)"', tf_code)
        return list(set(matches))

    async def _estimate_complexity(self, tf_code: str) -> str:
        """
        Estimates complexity based on the number of resources in the HCL.
        """
        all_resources = re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', tf_code)
        count = len(all_resources)
        
        if count <= 2:
            return "simple"
        elif count <= 5:
            return "moderate"
        else:
            return "complex"
