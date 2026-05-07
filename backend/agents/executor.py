"""
Executor Agent
--------------
The ExecutorAgent applies approved Terraform plans against the target AWS
account. It runs terraform init → plan → apply, streams real-time output to
the UI via WebSocket, and self-corrects on failure by calling the PlannerAgent
with the error context (up to 3 retries).
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

import boto3

from .models import AgentResult
from terraform.tf_validator import TerraformValidator

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class ExecutorAgent:
    """
    Applies approved Terraform plans and manages execution lifecycle.

    Responsibilities:
    - Run terraform init / plan / apply / destroy via async subprocess.
    - Stream stdout line-by-line to the WebSocket UI.
    - Self-correct on failure: send errors back to PlannerAgent and retry.
    - Restart EC2 services via AWS SSM Run Command.
    """

    def __init__(self, config, planner_agent=None, tf_runner=None, tf_state=None):
        """
        Parameters
        ----------
        config        : Settings
        planner_agent : PlannerAgent — used for self-correction on failure.
        tf_runner     : TerraformRunner — optional, for compatibility.
        tf_state      : TerraformState — optional, for state inspection.
        """
        self.config        = config
        self.planner       = planner_agent
        self.tf_runner     = tf_runner
        self.tf_state      = tf_state
        self.validator     = TerraformValidator()
        self.name          = "executor"
        self._ws_broadcast = None   # injected by API layer

    def set_ws_broadcaster(self, broadcast_fn):
        """Inject the WebSocket broadcast callable."""
        self._ws_broadcast = broadcast_fn

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self, input: dict) -> AgentResult:
        """
        Route to the correct execution method based on the 'action' key.

        Parameters
        ----------
        input : dict
            Must contain:
              action         : 'apply' | 'destroy' | 'plan'
              workspace_path : str — full path to terraform workspace directory
              request_id     : str — unique request identifier
              approved       : bool — must be True for destroy
        """
        action         = input.get("action", "plan")
        workspace_path = input.get("workspace_path", "")
        request_id     = input.get("request_id", "unknown")
        approved       = input.get("approved", False)

        if not workspace_path or not os.path.exists(workspace_path):
            return AgentResult(
                agent=self.name,
                severity="high",
                finding=f"Workspace path does not exist: '{workspace_path}'",
                recommended_action="Ensure the PlannerAgent created the workspace before calling ExecutorAgent.",
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"action": action, "request_id": request_id},
            )

        if action == "apply":
            return await self.execute_apply(workspace_path, request_id)
        elif action == "destroy":
            return await self.execute_destroy(workspace_path, request_id, approved=approved)
        elif action == "plan":
            return await self.execute_plan(workspace_path)
        else:
            return AgentResult(
                agent=self.name,
                severity="medium",
                finding=f"Unknown action '{action}'. Supported: apply, destroy, plan.",
                recommended_action="Specify a valid action.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={"action": action},
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Apply
    # ─────────────────────────────────────────────────────────────────────────

    async def execute_apply(self, workspace_path: str, request_id: str) -> AgentResult:
        """
        Run terraform init → terraform plan → terraform apply -auto-approve.

        On failure calls _self_correct() and retries up to MAX_RETRIES times.

        Returns
        -------
        AgentResult
            Describes what was created or the final error after all retries.
        """
        logger.info("[ExecutorAgent] execute_apply: request_id=%s", request_id)

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info("[ExecutorAgent] Apply attempt %d/%d", attempt, MAX_RETRIES)

            # ── terraform init ────────────────────────────────────────────
            if self.tf_runner:
                init_result = await self.tf_runner.init(workspace_path)
                init_ok = init_result.success
                init_err = init_result.stdout  # combined stdout+stderr
            else:
                init_ok, init_err = await self._run_cmd(
                    ["terraform", "init", "-no-color", "-input=false", "-backend=false"],
                    workspace_path, request_id, label="init"
                )
            if not init_ok:
                corrected = await self._self_correct(init_err, workspace_path, attempt)
                if corrected and attempt < MAX_RETRIES:
                    continue
                return self._error_result(
                    f"terraform init failed after {attempt} attempt(s).", init_err, attempt
                )

            # ── terraform plan ────────────────────────────────────────────
            if self.tf_runner:
                # Pass AWS credentials as variables to terraform plan
                variables = {
                    "aws_access_key": self.config.AWS_ACCESS_KEY_ID,
                    "aws_secret_key": self.config.AWS_SECRET_ACCESS_KEY,
                    "aws_region": self.config.AWS_DEFAULT_REGION,
                }
                plan_result = await self.tf_runner.plan(workspace_path, variables)
                plan_ok = plan_result.success
                plan_err = plan_result.stdout  # combined stdout+stderr
                plan_out = plan_result.stdout
            else:
                plan_ok, plan_out = await self._run_cmd(
                    ["terraform", "plan", "-no-color", "-input=false", "-out=tfplan"],
                    workspace_path, request_id, label="plan"
                )
                plan_err = plan_out
            if not plan_ok:
                corrected = await self._self_correct(plan_err, workspace_path, attempt)
                if corrected and attempt < MAX_RETRIES:
                    continue
                return self._error_result(
                    f"terraform plan failed after {attempt} attempt(s).", plan_err, attempt
                )

            # ── terraform apply ───────────────────────────────────────────
            if self.tf_runner:
                # Pass AWS credentials as variables to terraform apply
                variables = {
                    "aws_access_key": self.config.AWS_ACCESS_KEY_ID,
                    "aws_secret_key": self.config.AWS_SECRET_ACCESS_KEY,
                    "aws_region": self.config.AWS_DEFAULT_REGION,
                }
                apply_result = await self.tf_runner.apply(workspace_path, variables)
                apply_ok = apply_result.success
                apply_out = apply_result.stdout  # combined stdout+stderr
            else:
                apply_ok, apply_out = await self._run_cmd(
                    ["terraform", "apply", "-no-color", "-auto-approve", "tfplan"],
                    workspace_path, request_id, label="apply"
                )
            if not apply_ok:
                corrected = await self._self_correct(apply_out, workspace_path, attempt)
                if corrected and attempt < MAX_RETRIES:
                    continue
                return self._error_result(
                    f"terraform apply failed after {attempt} attempt(s).", apply_out, attempt
                )

            # ── Success ───────────────────────────────────────────────────
            logger.info("[ExecutorAgent] Apply succeeded on attempt %d.", attempt)
            return AgentResult(
                agent=self.name,
                severity="info",
                finding="Terraform apply completed successfully. All resources were created/updated.",
                recommended_action="Monitor deployed resources via the Monitor agent.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={
                    "request_id": request_id,
                    "workspace":  workspace_path,
                    "attempts":   attempt,
                },
            )

        # Exhausted retries
        return self._error_result(
            f"terraform apply failed after {MAX_RETRIES} attempts.",
            "All retry attempts exhausted.",
            MAX_RETRIES,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Plan
    # ─────────────────────────────────────────────────────────────────────────

    async def execute_plan(self, workspace_path: str) -> AgentResult:
        """
        Run terraform init + terraform plan and return the plan output.

        Returns
        -------
        AgentResult
            proposed_tf contains the raw plan output.
            estimated_cost_delta is parsed from the plan summary line.
        """
        request_id = os.path.basename(workspace_path)
        logger.info("[ExecutorAgent] execute_plan: %s", workspace_path)

        init_ok, init_err = await self._run_cmd(
            ["terraform", "init", "-no-color", "-input=false", "-backend=false"],
            workspace_path, request_id, label="init"
        )
        if not init_ok:
            return self._error_result("terraform init failed during plan.", init_err, 1)

        if self.tf_runner:
            # Pass AWS credentials as variables to terraform plan
            variables = {
                "aws_access_key": self.config.AWS_ACCESS_KEY_ID,
                "aws_secret_key": self.config.AWS_SECRET_ACCESS_KEY,
                "aws_region": self.config.AWS_DEFAULT_REGION,
            }
            plan_result = await self.tf_runner.plan(workspace_path, variables)
            plan_ok = plan_result.success
            plan_out = plan_result.stdout  # combined stdout+stderr
        else:
            plan_ok, plan_out = await self._run_cmd(
                ["terraform", "plan", "-no-color", "-input=false"],
                workspace_path, request_id, label="plan"
            )

        # Parse summary regardless of exit code (plan exits 1 when changes exist)
        from terraform.tf_validator import TerraformValidator
        parsed = TerraformValidator().parse_plan_output(plan_out)
        to_add = parsed.get("resources_to_add", 0)
        to_change = parsed.get("resources_to_change", 0)
        to_destroy = parsed.get("resources_to_destroy", 0)

        cost_delta = f"+~${to_add * 10:.2f}/mo (estimate)"  # rough heuristic

        return AgentResult(
            agent=self.name,
            severity="info" if to_destroy == 0 else "medium",
            finding=(
                f"Plan: {to_add} to add, {to_change} to change, {to_destroy} to destroy. "
                f"Resources: {', '.join(parsed.get('resource_list', [])) or 'none'}"
            ),
            recommended_action="Review the plan and approve to apply.",
            requires_human=True,
            proposed_tf=plan_out,
            estimated_cost_delta=cost_delta,
            timestamp=datetime.utcnow(),
            metadata={"plan_summary": parsed, "workspace": workspace_path},
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Destroy
    # ─────────────────────────────────────────────────────────────────────────

    async def execute_destroy(
        self, workspace_path: str, request_id: str, approved: bool = False
    ) -> AgentResult:
        """
        Run terraform destroy -auto-approve ONLY when approved=True.

        Always sets requires_human=True unless approved is explicitly passed.
        """
        logger.info("[ExecutorAgent] execute_destroy: approved=%s", approved)

        if not approved:
            return AgentResult(
                agent=self.name,
                severity="high",
                finding="Terraform destroy requested but human approval has not been granted.",
                recommended_action="Explicitly set approved=True in the request payload to confirm destroy.",
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"request_id": request_id, "workspace": workspace_path},
            )

        # Init first
        if self.tf_runner:
            init_result = await self.tf_runner.init(workspace_path)
            init_ok = init_result.success
            init_err = init_result.stdout  # combined stdout+stderr
        else:
            init_ok, init_err = await self._run_cmd(
                ["terraform", "init", "-no-color", "-input=false", "-backend=false"],
                workspace_path, request_id, label="init"
            )
        if not init_ok:
            return self._error_result("terraform init failed before destroy.", init_err, 1)

        if self.tf_runner:
            destroy_result = await self.tf_runner.destroy(workspace_path)
            destroy_ok = destroy_result.success
            destroy_out = destroy_result.stdout  # combined stdout+stderr
        else:
            destroy_ok, destroy_out = await self._run_cmd(
                ["terraform", "destroy", "-no-color", "-auto-approve", "-input=false"],
                workspace_path, request_id, label="destroy"
            )

        if not destroy_ok:
            return self._error_result("terraform destroy failed.", destroy_out, 1)

        return AgentResult(
            agent=self.name,
            severity="medium",
            finding="Terraform destroy completed. All managed resources have been removed.",
            recommended_action="Verify resources are removed in the AWS console.",
            requires_human=False,
            timestamp=datetime.utcnow(),
            metadata={"request_id": request_id, "workspace": workspace_path},
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Self-correction
    # ─────────────────────────────────────────────────────────────────────────

    async def _self_correct(
        self, error_output: str, workspace_path: str, attempt: int
    ) -> bool:
        """
        Send the error to PlannerAgent and overwrite workspace files with new HCL.

        Parameters
        ----------
        error_output   : str — stderr / stdout from the failed terraform command.
        workspace_path : str — path to the current workspace directory.
        attempt        : int — current attempt number (1-based).

        Returns
        -------
        bool
            True if the PlannerAgent produced new code; False if it could not.
        """
        if self.planner is None:
            logger.warning("[ExecutorAgent] No PlannerAgent available for self-correction.")
            return False

        logger.info("[ExecutorAgent] _self_correct attempt=%d, sending error to PlannerAgent.", attempt)

        # Read current main.tf to include as context
        main_tf_path = os.path.join(workspace_path, "main.tf")
        current_hcl = ""
        try:
            with open(main_tf_path, "r", encoding="utf-8") as f:
                current_hcl = f.read()
        except OSError:
            pass

        result: AgentResult = await self.planner.run({
            "action":        "fix_error",
            "error":         error_output,
            "attempt":       attempt,
            "current_hcl":   current_hcl,
            "request":       f"Fix this Terraform error (attempt {attempt}):\n{error_output}",
            "intent":        f"Fix Terraform error: {error_output[:200]}",
        })

        new_hcl = result.proposed_tf
        if not new_hcl or not new_hcl.strip():
            logger.warning("[ExecutorAgent] Self-correction produced no new code.")
            return False

        # Overwrite main.tf with corrected code
        try:
            with open(main_tf_path, "w", encoding="utf-8") as f:
                f.write(new_hcl)
            logger.info("[ExecutorAgent] Workspace main.tf overwritten with corrected code.")
            return True
        except OSError as exc:
            logger.error("[ExecutorAgent] Failed to overwrite workspace: %s", exc)
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # SSM service restart
    # ─────────────────────────────────────────────────────────────────────────

    async def restart_service(self, instance_id: str, service_name: str) -> AgentResult:
        """
        Use boto3 SSM to send AWS-RunShellScript to restart a systemd service.

        Parameters
        ----------
        instance_id  : str — EC2 instance ID (e.g. 'i-0abc123def456').
        service_name : str — systemd service name (e.g. 'nginx', 'myapp').

        Returns
        -------
        AgentResult
            Describes the SSM command result.
        """
        logger.info("[ExecutorAgent] restart_service: instance=%s service=%s", instance_id, service_name)

        try:
            ssm = boto3.client(
                "ssm",
                aws_access_key_id=self.config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.config.AWS_SECRET_ACCESS_KEY,
                region_name=self.config.AWS_DEFAULT_REGION,
            )

            response = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={
                    "commands": [
                        f"sudo systemctl restart {service_name}",
                        f"sudo systemctl status {service_name} --no-pager",
                    ]
                },
                Comment=f"InfraGenie restart: {service_name}",
            )

            command_id = response["Command"]["CommandId"]
            logger.info("[ExecutorAgent] SSM command sent: %s", command_id)

            return AgentResult(
                agent=self.name,
                severity="info",
                finding=(
                    f"SSM Run Command sent to restart '{service_name}' on instance '{instance_id}'. "
                    f"Command ID: {command_id}"
                ),
                recommended_action=f"Check SSM command status for command ID {command_id}.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={
                    "command_id":  command_id,
                    "instance_id": instance_id,
                    "service":     service_name,
                },
            )
        except Exception as exc:
            logger.error("[ExecutorAgent] SSM restart_service failed: %s", exc)
            return AgentResult(
                agent=self.name,
                severity="high",
                finding=f"Failed to restart service '{service_name}' on '{instance_id}': {exc}",
                recommended_action="Check AWS credentials and SSM agent status on the instance.",
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"error": str(exc), "instance_id": instance_id, "service": service_name},
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_cmd(
        self,
        cmd: list[str],
        cwd: str,
        request_id: str,
        label: str = "",
    ) -> tuple[bool, str]:
        """
        Run a subprocess command, stream output line-by-line, and return result.

        Parameters
        ----------
        cmd        : list[str] — command + args (never shell=True)
        cwd        : str       — working directory
        request_id : str       — used for WS tagging
        label      : str       — human label for log messages

        Returns
        -------
        tuple[bool, str]
            (success, combined_stdout_stderr)
        """
        logger.info("[ExecutorAgent] Running [%s]: %s", label, " ".join(cmd))
        collected = []

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # merge stderr into stdout
            )

            await self._stream_output(proc, request_id, label=label, collector=collected)
            await proc.wait()

            output = "\n".join(collected)
            success = proc.returncode == 0
            if not success:
                logger.warning("[ExecutorAgent] [%s] exited with code %d.", label, proc.returncode)
            return success, output

        except FileNotFoundError:
            msg = "terraform CLI not found. Please install Terraform."
            logger.error("[ExecutorAgent] %s", msg)
            return False, msg
        except Exception as exc:
            logger.exception("[ExecutorAgent] Unexpected error in _run_cmd [%s]: %s", label, exc)
            return False, str(exc)

    async def _stream_output(
        self,
        process: asyncio.subprocess.Process,
        request_id: str,
        label: str = "",
        collector: Optional[list] = None,
    ):
        """
        Read subprocess stdout line by line and emit each line via WebSocket.

        Parameters
        ----------
        process    : asyncio subprocess
        request_id : str  — included in each WS payload for UI routing
        label      : str  — command label (init/plan/apply/destroy)
        collector  : list — if provided, lines are also appended here
        """
        if process.stdout is None:
            return

        async for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if collector is not None:
                collector.append(line)

            logger.debug("[ExecutorAgent][%s] %s", label, line)

            if self._ws_broadcast is not None:
                payload = json.dumps({
                    "type":       "terraform_log",
                    "request_id": request_id,
                    "label":      label,
                    "line":       line,
                    "timestamp":  datetime.utcnow().isoformat(),
                })
                try:
                    await self._ws_broadcast(payload)
                except Exception as exc:
                    logger.debug("[ExecutorAgent] WS broadcast error: %s", exc)

    def _error_result(self, finding: str, error_detail: str, attempts: int) -> AgentResult:
        """Convenience builder for error AgentResult."""
        full_finding = finding
        if error_detail and error_detail.strip():
            full_finding = f"{finding}\n\nError details: {error_detail}"
        return AgentResult(
            agent=self.name,
            severity="high",
            finding=full_finding,
            recommended_action="Review the error details and correct the Terraform configuration.",
            requires_human=True,
            timestamp=datetime.utcnow(),
            metadata={"error": error_detail, "attempts": attempts},
        )
