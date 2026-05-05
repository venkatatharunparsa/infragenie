"""
Terraform Validator
Validates Terraform workspaces and parses plan outputs.
"""

import asyncio
import os
import re

class TerraformValidator:
    async def validate_syntax(self, workspace_path: str) -> tuple[bool, str]:
        """Runs subprocess 'terraform init -backend=false' then 'terraform validate'."""
        if not os.path.exists(workspace_path):
            return False, f"Workspace path does not exist: {workspace_path}"

        try:
            init_proc = await asyncio.create_subprocess_exec(
                "terraform", "init", "-backend=false",
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await init_proc.communicate()
            
            val_proc = await asyncio.create_subprocess_exec(
                "terraform", "validate", "-no-color",
                cwd=workspace_path,
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
            return False, "Terraform CLI not found on the system."
        except Exception as e:
            return False, str(e)

    def parse_plan_output(self, plan_output: str) -> dict:
        """Parses 'terraform plan' stdout into structured dict."""
        result = {
            "resources_to_add": 0,
            "resources_to_change": 0,
            "resources_to_destroy": 0,
            "resource_list": []
        }
        
        # Parse Plan: X to add, Y to change, Z to destroy.
        summary_match = re.search(r'Plan:\s+(\d+)\s+to add,\s+(\d+)\s+to change,\s+(\d+)\s+to destroy', plan_output)
        if summary_match:
            result["resources_to_add"] = int(summary_match.group(1))
            result["resources_to_change"] = int(summary_match.group(2))
            result["resources_to_destroy"] = int(summary_match.group(3))
            
        # Parse resource actions, e.g. # aws_instance.web will be created
        resource_matches = re.findall(r'# ([\w\.\-]+) will be (created|updated in-place|destroyed|read)', plan_output)
        for res, action in resource_matches:
            result["resource_list"].append(f"{res} ({action})")
            
        return result
