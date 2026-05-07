"""
ChromaDB RAG Client
-------------------
Complete RAG (Retrieval-Augmented Generation) pipeline for InfraGenie.

Uses ChromaDB for vector storage and Google Gemini text-embedding-004 for
embeddings. Maintains six specialised collections covering deployment history,
Terraform patterns, incidents, AWS best practices, security policies, and
cost intelligence.
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from google import genai
from backend.utils.genai_client import GenAIClientPool

logger = logging.getLogger(__name__)

# Collection names used across the RAG pipeline
COLLECTION_NAMES = [
    "deployment_history",
    "terraform_patterns",
    "incident_log",
    "aws_best_practices",
    "security_policies",
    "cost_intelligence",
]


class ChromaRAGClient:
    """Full-featured RAG client backed by ChromaDB and Gemini embeddings.

    Responsibilities
    ----------------
    * Embed text via the Gemini ``models/text-embedding-004`` model.
    * Store and retrieve deployment history, Terraform patterns, incidents,
      AWS best practices, security policies, and cost intelligence.
    * Format retrieved context into a structured prompt section for Gemini.
    """

    # -----------------------------------------------------------------
    # Initialisation
    # -----------------------------------------------------------------

    def __init__(self, persist_dir: str, gemini_api_key: str, fallback_key: Optional[str] = None):
        """
        Parameters
        ----------
        persist_dir    : str — filesystem path for ChromaDB persistence.
        gemini_api_key : str — Google Gemini API key for embeddings.
        fallback_key   : str — Optional fallback key.
        """
        self.persist_dir = persist_dir
        self.gemini_api_key = gemini_api_key
        self.fallback_key = fallback_key

        # Configure the Gemini SDK pool
        self.client_pool = GenAIClientPool(
            primary_key=self.gemini_api_key,
            fallback_key=self.fallback_key
        )
        self.embedding_model = "models/gemini-embedding-2"

        # Initialise ChromaDB persistent client
        self.chroma = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Pre-create all six collections
        self.collections: dict[str, Any] = {}
        for name in COLLECTION_NAMES:
            self.collections[name] = self.chroma.get_or_create_collection(name=name)

        logger.info(
            "[ChromaRAGClient] Initialised with %d collections at %s",
            len(self.collections),
            self.persist_dir,
        )

    # -----------------------------------------------------------------
    # Embedding
    # -----------------------------------------------------------------

    async def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        """Embed *text* using Gemini ``text-embedding-004``.

        Parameters
        ----------
        text      : str — the text to embed.
        task_type : str — ``RETRIEVAL_DOCUMENT`` for storage,
                         ``RETRIEVAL_QUERY`` for search queries.

        Returns
        -------
        list[float] — dense embedding vector.
        """
        try:
            result = await asyncio.to_thread(
                self.client_pool.embed_content,
                model=self.embedding_model,
                contents=text,
                config={'task_type': task_type},
            )
            return result.embeddings[0].values
        except Exception as exc:
            logger.error("[ChromaRAGClient] embed() failed: %s", exc)
            raise

    # -----------------------------------------------------------------
    # Storage helpers
    # -----------------------------------------------------------------

    async def store_deployment(
        self,
        request_id: str,
        user_request: str,
        tf_code: str,
        result: Any,  # AgentResult — kept as Any to avoid circular imports
    ):
        """Embed and store a completed deployment in ``deployment_history``.

        Parameters
        ----------
        request_id   : str — unique request identifier.
        user_request : str — the original human request.
        tf_code      : str — the generated Terraform HCL.
        result       : AgentResult — outcome of the deployment.
        """
        summary = f"{user_request}\n\nResult: {result.finding}"
        embedding = await self.embed(summary, task_type="RETRIEVAL_DOCUMENT")

        resource_types = self._extract_resource_types(tf_code)
        success = result.severity.lower() not in ("critical", "high")

        collection = self.collections["deployment_history"]
        await asyncio.to_thread(
            collection.upsert,
            ids=[request_id],
            embeddings=[embedding],
            documents=[summary],
            metadatas=[{
                "request_id":     request_id,
                "success":        str(success),
                "timestamp":      datetime.utcnow().isoformat(),
                "resource_types": ",".join(resource_types),
                "tf_code":        tf_code[:10000],  # ChromaDB metadata value limit
                "user_request":   user_request[:2000],
            }],
        )
        logger.info("[ChromaRAGClient] Stored deployment %s (success=%s)", request_id, success)

    async def store_incident(
        self,
        incident_description: str,
        resolution: str,
        severity: str,
    ):
        """Embed and store an incident in ``incident_log``.

        Parameters
        ----------
        incident_description : str — what happened.
        resolution           : str — how it was resolved.
        severity             : str — incident severity.
        """
        embedding = await self.embed(incident_description, task_type="RETRIEVAL_DOCUMENT")
        doc_id = str(uuid.uuid4())

        collection = self.collections["incident_log"]
        await asyncio.to_thread(
            collection.upsert,
            ids=[doc_id],
            embeddings=[embedding],
            documents=[incident_description],
            metadatas=[{
                "resolution": resolution[:5000],
                "severity":   severity,
                "timestamp":  datetime.utcnow().isoformat(),
                "resolved":   "true",
            }],
        )
        logger.info("[ChromaRAGClient] Stored incident %s (severity=%s)", doc_id, severity)

    # -----------------------------------------------------------------
    # Retrieval helpers
    # -----------------------------------------------------------------

    async def retrieve_similar_deployments(
        self, user_request: str, top_k: int = 5
    ) -> list[dict]:
        """Find the *top_k* most similar past deployments.

        Returns a list of dicts each containing ``document``, ``metadata``,
        and ``distance`` (lower is more similar).
        """
        return await self._query_collection(
            "deployment_history", user_request, top_k
        )

    async def retrieve_patterns(
        self, user_request: str, top_k: int = 3
    ) -> list[dict]:
        """Find the *top_k* most relevant Terraform patterns."""
        return await self._query_collection(
            "terraform_patterns", user_request, top_k
        )

    async def retrieve_incidents(
        self, situation: str, top_k: int = 3
    ) -> list[dict]:
        """Find the *top_k* most similar past incidents and their resolutions."""
        return await self._query_collection(
            "incident_log", situation, top_k
        )

    async def retrieve_best_practices(
        self, topic: str, top_k: int = 3
    ) -> list[dict]:
        """Find the *top_k* most relevant AWS best-practice documents."""
        return await self._query_collection(
            "aws_best_practices", topic, top_k
        )

    async def _query_collection(
        self, collection_name: str, query_text: str, top_k: int
    ) -> list[dict]:
        """Internal: embed *query_text* and search *collection_name*.

        Uses ``RETRIEVAL_QUERY`` task type for the embedding.
        """
        collection = self.collections.get(collection_name)
        if collection is None:
            logger.warning("[ChromaRAGClient] Collection '%s' not found.", collection_name)
            return []

        # Check that the collection has documents
        count = collection.count()
        if count == 0:
            logger.debug("[ChromaRAGClient] Collection '%s' is empty.", collection_name)
            return []

        # Clamp top_k to actual document count
        effective_k = min(top_k, count)

        try:
            query_embedding = await self.embed(query_text, task_type="RETRIEVAL_QUERY")
            results = await asyncio.to_thread(
                collection.query,
                query_embeddings=[query_embedding],
                n_results=effective_k,
            )
        except Exception as exc:
            logger.error(
                "[ChromaRAGClient] Query failed on '%s': %s", collection_name, exc
            )
            return []

        # Unpack ChromaDB's nested list structure
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids       = results.get("ids", [[]])[0]

        output = []
        for i, doc in enumerate(documents):
            output.append({
                "id":       ids[i] if i < len(ids) else None,
                "document": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None,
            })
        return output

    # -----------------------------------------------------------------
    # Context formatting
    # -----------------------------------------------------------------

    async def format_rag_context(self, user_request: str) -> str:
        """Build a structured context string for injection into a Gemini prompt.

        Queries three collections in parallel and formats results under
        section headers: ``PAST DEPLOYMENTS``, ``PROVEN PATTERNS``,
        ``AWS BEST PRACTICES``.
        """
        deployments, patterns, best_practices = await asyncio.gather(
            self.retrieve_similar_deployments(user_request, top_k=5),
            self.retrieve_patterns(user_request, top_k=3),
            self.retrieve_best_practices(user_request, top_k=3),
        )

        sections: list[str] = []

        # ── PAST DEPLOYMENTS ──────────────────────────────────────────
        sections.append("=== PAST DEPLOYMENTS ===")
        if deployments:
            for i, dep in enumerate(deployments, 1):
                meta = dep.get("metadata", {})
                sections.append(
                    f"[{i}] Request: {meta.get('user_request', 'N/A')}\n"
                    f"    Resources: {meta.get('resource_types', 'N/A')}\n"
                    f"    Success: {meta.get('success', 'N/A')}\n"
                    f"    Terraform:\n{meta.get('tf_code', 'N/A')[:2000]}"
                )
        else:
            sections.append("No similar past deployments found.")

        # ── PROVEN PATTERNS ───────────────────────────────────────────
        sections.append("\n=== PROVEN PATTERNS ===")
        if patterns:
            for i, pat in enumerate(patterns, 1):
                sections.append(f"[{i}] {pat.get('document', 'N/A')[:1500]}")
        else:
            sections.append("No matching Terraform patterns found.")

        # ── AWS BEST PRACTICES ────────────────────────────────────────
        sections.append("\n=== AWS BEST PRACTICES ===")
        if best_practices:
            for i, bp in enumerate(best_practices, 1):
                sections.append(f"[{i}] {bp.get('document', 'N/A')[:1500]}")
        else:
            sections.append("No matching AWS best practices found.")

        return "\n".join(sections)

    # -----------------------------------------------------------------
    # Collection stats
    # -----------------------------------------------------------------

    async def get_collection_stats(self) -> dict:
        """Return the document count for every collection.

        Returns
        -------
        dict — ``{collection_name: int, ...}``
        """
        stats: dict[str, int] = {}
        for name, col in self.collections.items():
            try:
                stats[name] = await asyncio.to_thread(col.count)
            except Exception as exc:
                logger.warning("[ChromaRAGClient] count() failed for '%s': %s", name, exc)
                stats[name] = -1
        return stats

    # -----------------------------------------------------------------
    # Internal utilities
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_resource_types(tf_code: str) -> list[str]:
        """Pull distinct ``resource "<type>"`` identifiers from HCL code."""
        matches = re.findall(r'resource\s+"([^"]+)"', tf_code)
        return sorted(set(matches))


# ---------------------------------------------------------------------------
# Backwards-compatible module-level helpers (used by knowledge_loader etc.)
# ---------------------------------------------------------------------------

_client = None


def get_chroma_client(persist_dir: str = "./chroma_db") -> chromadb.ClientAPI:
    """Return a singleton ChromaDB persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_or_create_collection(name: str, persist_dir: str = "./chroma_db"):
    """Get or create a named ChromaDB collection."""
    client = get_chroma_client(persist_dir)
    return client.get_or_create_collection(name=name)
