"""
Terraform Runner
Wraps the Terraform CLI via asyncio subprocess to execute commands within
a specific workspace directory.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class TerraformTimeoutError(Exception):
    """Raised when a Terraform command exceeds the maximum execution time."""
    pass

@dataclass
class TerraformResult:
    """Standardized result for Terraform CLI command execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float

class TerraformRunner:
    """Wraps the Terraform CLI for programmatic use via asyncio."""

    def __init__(self, terraform_binary: str = "terraform"):
        """
        Initialize the TerraformRunner.
        
        Parameters
        ----------
        terraform_binary : str
            Path to the terraform executable or just 'terraform' if in PATH.
        """
        self.terraform_binary = terraform_binary
        self.timeout = 600  # 10 minutes maximum

    async def _run_command(self, workspace_path: str, args: list[str]) -> TerraformResult:
        """
        Internal helper to execute a command with timeout and capture output.
        """
        cmd_str = f"{self.terraform_binary} {' '.join(args)}"
        logger.info(f"[TerraformRunner] Running in {workspace_path}: {cmd_str}")
        
        start_time = time.monotonic()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.terraform_binary,
                *args,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for command completion with timeout
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), 
                timeout=self.timeout
            )
            
        except asyncio.TimeoutError:
            duration = time.monotonic() - start_time
            logger.error(f"[TerraformRunner] Timeout after {duration:.2f}s: {cmd_str}")
            
            # Attempt to kill the process if it timed out
            try:
                proc.kill()
                await proc.wait()
            except Exception as e:
                logger.warning(f"[TerraformRunner] Failed to kill timed out process: {e}")
                
            raise TerraformTimeoutError(f"Command '{cmd_str}' timed out after {self.timeout} seconds.")
            
        except Exception as e:
            duration = time.monotonic() - start_time
            logger.exception(f"[TerraformRunner] Error executing {cmd_str}: {e}")
            return TerraformResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_seconds=duration
            )

        duration = time.monotonic() - start_time
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        
        # Determine success
        # 'plan -detailed-exitcode' returns 2 when there are changes, which is success
        success = proc.returncode == 0
        if "plan" in args and "-detailed-exitcode" in args and proc.returncode == 2:
            success = True
            
        logger.debug(f"[TerraformRunner] Completed with code {proc.returncode} in {duration:.2f}s")
            
        return TerraformResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            duration_seconds=duration
        )

    async def init(self, workspace_path: str) -> TerraformResult:
        """Run 'terraform init' in the given workspace."""
        args = ["init", "-input=false", "-no-color"]
        return await self._run_command(workspace_path, args)

    async def plan(self, workspace_path: str) -> TerraformResult:
        """Run 'terraform plan' in the given workspace."""
        args = ["plan", "-input=false", "-no-color", "-detailed-exitcode"]
        return await self._run_command(workspace_path, args)

    async def apply(self, workspace_path: str) -> TerraformResult:
        """Run 'terraform apply' in the given workspace."""
        args = ["apply", "-auto-approve", "-input=false", "-no-color"]
        return await self._run_command(workspace_path, args)

    async def destroy(self, workspace_path: str) -> TerraformResult:
        """Run 'terraform destroy' in the given workspace."""
        args = ["destroy", "-auto-approve", "-input=false", "-no-color"]
        return await self._run_command(workspace_path, args)

    async def validate(self, workspace_path: str) -> TerraformResult:
        """Run 'terraform validate' in the given workspace."""
        args = ["validate", "-no-color"]
        return await self._run_command(workspace_path, args)

    async def output(self, workspace_path: str) -> dict:
        """Run 'terraform output -json' and parse the result."""
        args = ["output", "-json"]
        result = await self._run_command(workspace_path, args)
        
        if not result.success and result.exit_code != 0:
            logger.warning(f"[TerraformRunner] output command failed: {result.stderr}")
            return {}
            
        try:
            if not result.stdout.strip():
                return {}
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"[TerraformRunner] Failed to parse output JSON: {e}")
            return {}

    async def state_list(self, workspace_path: str) -> list[str]:
        """Run 'terraform state list' and return list of resource addresses."""
        args = ["state", "list"]
        result = await self._run_command(workspace_path, args)
        
        if not result.success and result.exit_code != 0:
            logger.warning(f"[TerraformRunner] state list failed: {result.stderr}")
            return []
            
        resources = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return resources
