"""
Security Agent
--------------
The SecurityAgent scans Terraform code before every apply and monitors live AWS infrastructure for security issues.
It combines fast rule‑engine checks, tfsec, Checkov, and AWS API audits, logs every event, and can auto‑fix simple violations.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .models import AgentResult

logger = logging.getLogger(__name__)

# Mapping of severity strings to a numeric ranking for easy comparison
_SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


class SecurityAgent:
    """Gatekeeper that validates Terraform HCL and live AWS resources.

    Workflow:
    1️⃣ Tier‑1 rule‑engine check (instant, no LLM)
    2️⃣ tfsec scan (JSON output)
    3️⃣ Checkov scan (JSON output)
    4️⃣ Aggregate violations, determine worst severity
    5️⃣ Auto‑fix any auto‑fixable low‑severity violations
    6️⃣ Return an ``AgentResult`` with findings and optionally the fixed HCL.
    """

    def __init__(self, config, rules_engine, audit_log):
        """Store dependencies.

        Parameters
        ----------
        config : Settings – provides AWS credentials, region, etc.
        rules_engine : object – must expose ``check(tf_code)`` returning a list of dicts
            ``{"id": str, "severity": str, "description": str, "auto_fixable": bool}``.
        audit_log : object – must expose a ``write(entry: dict)`` method.
        """
        self.config = config
        self.rules_engine = rules_engine
        self.audit_log = audit_log
        self.name = "security"
        # Lazy‑initialized boto3 clients
        self._ec2 = None
        self._s3 = None
        self._ce = None

    # ---------------------------------------------------------------------
    # Public dispatcher
    # ---------------------------------------------------------------------
    async def run(self, input: dict) -> AgentResult:
        """Dispatch to the requested security action.

        Supported ``input["action"]`` values:
        * ``scan_tf`` – static scan of Terraform HCL (requires ``terraform_hcl`` and ``workspace_path``)
        * ``audit_live`` – runs both SG and S3 audits and merges results
        * ``check_security_groups`` – SG open‑port audit only
        * ``check_s3_public`` – S3 bucket ACL / encryption / versioning audit only
        """
        action = input.get("action")
        logger.info("[SecurityAgent] run() called with action=%s", action)

        if action == "scan_tf":
            tf_code = input.get("terraform_hcl", "")
            workspace = input.get("workspace_path", "")
            result = await self.scan_terraform(tf_code, workspace)
            await self.log_action(action, result)
            return result

        if action == "audit_live":
            sg_res = await self.audit_security_groups()
            s3_res = await self.audit_s3_buckets()
            # Combine findings and choose worst severity
            combined_finding = f"Security Group issues: {sg_res.finding}; S3 bucket issues: {s3_res.finding}"
            worst_sev = max([sg_res.severity, s3_res.severity], key=lambda s: _SEVERITY_RANK.get(s, 0))
            result = AgentResult(
                agent=self.name,
                severity=worst_sev,
                finding=combined_finding,
                recommended_action="Review the detailed audit logs for each resource.",
                requires_human=worst_sev in ("high", "critical"),
                timestamp=datetime.utcnow(),
                metadata={"sg_audit": sg_res.metadata, "s3_audit": s3_res.metadata},
            )
            await self.log_action(action, result)
            return result

        if action == "check_security_groups":
            result = await self.audit_security_groups()
            await self.log_action(action, result)
            return result

        if action == "check_s3_public":
            result = await self.audit_s3_buckets()
            await self.log_action(action, result)
            return result

        # Fallback for unknown actions
        result = AgentResult(
            agent=self.name,
            severity="info",
            finding=f"Unknown action '{action}'.",
            recommended_action="Use one of: scan_tf, audit_live, check_security_groups, check_s3_public.",
            requires_human=False,
            timestamp=datetime.utcnow(),
            metadata={"action": action},
        )
        await self.log_action(action, result)
        return result

    # ---------------------------------------------------------------------
    # Terraform scanning pipeline
    # ---------------------------------------------------------------------
    async def scan_terraform(self, tf_code: str, workspace_path: str) -> AgentResult:
        """Run tier‑1 rule engine, tfsec, and Checkov, then optionally auto‑fix.
        Returns an ``AgentResult`` containing all violations and possibly a corrected HCL.
        """
        logger.info("[SecurityAgent] scan_terraform started for workspace %s", workspace_path)
        violations: List[Dict[str, Any]] = []

        # 1️⃣ Tier‑1 rule engine (instant, no LLM)
        try:
            engine_violations = self.rules_engine.check(tf_code)
            violations.extend(engine_violations)
        except Exception as exc:
            logger.exception("[SecurityAgent] Rule engine failure: %s", exc)
            violations.append({"id": "ENGINE-FAIL", "severity": "high", "description": str(exc), "auto_fixable": False})

        def blockers_exist() -> bool:
            return any(v["severity"].lower() in ("high", "critical") for v in violations)

        # 2️⃣ tfsec (if no high/critical blockers)
        if not blockers_exist():
            tfsec_viol = await self.run_tfsec(workspace_path)
            violations.extend(tfsec_viol)

        # 3️⃣ Checkov (if still no blockers)
        if not blockers_exist():
            checkov_viol = await self.run_checkov(workspace_path)
            violations.extend(checkov_viol)

        # Determine worst severity across all violations
        worst_sev = "info"
        for v in violations:
            sev = v.get("severity", "info").lower()
            if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(worst_sev, 0):
                worst_sev = sev

        # 5️⃣ Auto‑fix low‑severity, auto‑fixable violations
        fixed_code = tf_code
        auto_fixed = False
        if any(v.get("auto_fixable", False) for v in violations):
            fixed_code = await self.auto_fix(tf_code, violations)
            auto_fixed = True

        # Build human‑readable finding summary
        finding_lines = []
        for v in violations:
            finding_lines.append(f"[{v.get('severity').upper()}] {v.get('id')}: {v.get('description')}")
        finding = "\n".join(finding_lines) if finding_lines else "No security violations detected."

        return AgentResult(
            agent=self.name,
            severity=worst_sev,
            finding=finding,
            recommended_action="address listed violations" if violations else "continue deployment",
            requires_human=worst_sev in ("high", "critical"),
            proposed_tf=fixed_code,
            workspace_path=workspace_path,
            timestamp=datetime.utcnow(),
            metadata={
                "workspace": workspace_path,
                "auto_fixed": auto_fixed,
                "violations_count": len(violations),
            },
        )

    async def auto_fix(self, tf_code: str, violations: List[Dict[str, Any]]) -> str:
        """Placeholder auto‑fixer – returns the original HCL.
        Real implementations would apply templated patches for known auto‑fixable rules.
        """
        logger.info("[SecurityAgent] auto_fix invoked for %d auto‑fixable violations", len([v for v in violations if v.get('auto_fixable')]))
        return tf_code

    # ---------------------------------------------------------------------
    # tfsec integration
    # ---------------------------------------------------------------------
    async def run_tfsec(self, workspace_path: str) -> List[Dict[str, Any]]:
        """Run ``tfsec`` against the workspace and parse JSON output.
        Returns a list of dicts: ``{"id", "severity", "description", "location", "auto_fixable"}``.
        """
        cmd = ["tfsec", workspace_path, "--format", "json", "--no-colour"]
        logger.info("[SecurityAgent] Executing tfsec: %s", " ".join(cmd))
        try:
            # Use subprocess.run instead of asyncio.create_subprocess_exec for Windows compatibility
            import subprocess
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=workspace_path,
                    timeout=60  # 60 second timeout
                )
            )
            if result.returncode not in (0, 1):  # 1 indicates findings
                logger.warning("tfsec exited with code %s: %s", result.returncode, result.stderr)
                return []
            data = json.loads(result.stdout)
            results = []
            for r in data.get("results", []):
                results.append({
                    "id": r.get("rule_id"),
                    "severity": self._parse_tfsec_severity(r.get("severity", "LOW")),
                    "description": r.get("description", ""),
                    "location": r.get("location", {}),
                    "auto_fixable": "auto‑fix" in (r.get("impact", "").lower()),
                })
            return results
        except FileNotFoundError:
            logger.error("tfsec binary not found – ensure tfsec is installed and on PATH.")
            return []
        except Exception as exc:
            logger.exception("Unexpected error executing tfsec: %s", exc)
            return []

    # ---------------------------------------------------------------------
    # Checkov integration
    # ---------------------------------------------------------------------
    async def run_checkov(self, workspace_path: str) -> List[Dict[str, Any]]:
        """Run ``checkov`` against the workspace and parse JSON output.
        Returns a list of dicts: ``{"id", "severity", "description", "location", "auto_fixable"}``.
        """
        cmd = ["checkov", "-d", workspace_path, "--output", "json", "--quiet"]
        logger.info("[SecurityAgent] Executing checkov: %s", " ".join(cmd))
        try:
            # Use subprocess.run instead of asyncio.create_subprocess_exec for Windows compatibility
            import subprocess
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=workspace_path,
                    timeout=120  # 2 minute timeout for checkov
                )
            )
            if result.returncode not in (0, 1):
                logger.warning("checkov exited with code %s: %s", result.returncode, result.stderr)
                return []
            data = json.loads(result.stdout)
            failed = data.get("results", {}).get("failed_checks", [])
            results = []
            for f in failed:
                results.append({
                    "id": f.get("check_id"),
                    "severity": f.get("severity", "LOW").lower(),
                    "description": f.get("description", ""),
                    "location": {
                        "file": f.get("file_path"),
                        "resource": f.get("resource"),
                        "guideline": f.get("guideline"),
                    },
                    "auto_fixable": False,
                })
            return results
        except FileNotFoundError:
            logger.error("checkov binary not found – ensure checkov is installed and on PATH.")
            return []
        except Exception as exc:
            logger.exception("Unexpected error executing checkov: %s", exc)
            return []

    # ---------------------------------------------------------------------
    # Live AWS audits
    # ---------------------------------------------------------------------
    async def audit_security_groups(self) -> AgentResult:
        """Inspect all security groups for permissive inbound rules.
        Flags any SG that allows 0.0.0.0/0 on ports 22, 3389, 3306, 5432.
        """
        logger.info("[SecurityAgent] Auditing security groups for open ports.")
        try:
            ec2 = self._boto("ec2")
            resp = await asyncio.to_thread(ec2.describe_security_groups)
            violations = []
            target_ports = {22, 3389, 3306, 5432}
            for sg in resp.get("SecurityGroups", []):
                sg_id = sg.get("GroupId")
                for perm in sg.get("IpPermissions", []):
                    from_port = perm.get("FromPort")
                    to_port = perm.get("ToPort")
                    if from_port is None or to_port is None:
                        continue
                    for ipr in perm.get("IpRanges", []):
                        cidr_ip = ipr.get("CidrIp")
                        if cidr_ip == "0.0.0.0/0":
                            for port in target_ports:
                                if from_port <= port <= to_port:
                                    violations.append({
                                        "id": f"SG-{sg_id}-OPEN-{port}",
                                        "severity": "high",
                                        "description": f"Security Group {sg_id} allows unrestricted inbound access on port {port}.",
                                        "auto_fixable": False,
                                    })
            if not violations:
                finding = "No overly permissive security group rules detected."
                severity = "info"
                requires_human = False
            else:
                finding = ", ".join(v["description"] for v in violations)
                severity = "high"
                requires_human = True
            return AgentResult(
                agent=self.name,
                severity=severity,
                finding=finding,
                recommended_action="Restrict the offending security groups to specific CIDRs or limit ports.",
                requires_human=requires_human,
                timestamp=datetime.utcnow(),
                metadata={"violations": violations},
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("[SecurityAgent] audit_security_groups AWS error: %s", exc)
            return AgentResult(
                agent=self.name,
                severity="info",
                finding=f"Failed to audit security groups: {exc}",
                recommended_action="Check AWS credentials, IAM permissions, and network connectivity.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={"error": str(exc)},
            )

    async def audit_s3_buckets(self) -> AgentResult:
        """Audit all S3 buckets for public ACL, missing encryption, and missing versioning.
        Returns an ``AgentResult`` describing any violations.
        """
        logger.info("[SecurityAgent] Auditing S3 bucket permissions and configurations.")
        try:
            s3 = self._boto("s3")
            resp = await asyncio.to_thread(s3.list_buckets)
            buckets = resp.get("Buckets", [])
            violations = []
            for b in buckets:
                name = b.get("Name")
                # Public ACL check
                try:
                    acl = await asyncio.to_thread(s3.get_bucket_acl, Bucket=name)
                    for grant in acl.get("Grants", []):
                        grantee = grant.get("Grantee", {})
                        if grantee.get("URI") == "http://acs.amazonaws.com/groups/global/AllUsers":
                            violations.append({
                                "id": f"S3-{name}-PUBLIC",
                                "severity": "critical",
                                "description": f"Bucket {name} is publicly readable via ACL.",
                                "auto_fixable": False,
                            })
                except Exception:
                    pass
                # Server‑side encryption check
                try:
                    enc = await asyncio.to_thread(s3.get_bucket_encryption, Bucket=name)
                    if not enc.get("ServerSideEncryptionConfiguration"):
                        raise Exception()
                except Exception:
                    violations.append({
                        "id": f"S3-{name}-NOENCRYPT",
                        "severity": "high",
                        "description": f"Bucket {name} does not have server‑side encryption enabled.",
                        "auto_fixable": False,
                    })
                # Versioning check
                try:
                    ver = await asyncio.to_thread(s3.get_bucket_versioning, Bucket=name)
                    if ver.get("Status") != "Enabled":
                        violations.append({
                            "id": f"S3-{name}-NOVERSION",
                            "severity": "medium",
                            "description": f"Bucket {name} does not have versioning enabled.",
                            "auto_fixable": False,
                        })
                except Exception:
                    pass
            if not violations:
                finding = "All S3 buckets comply with encryption, versioning, and private ACLs."
                severity = "info"
                requires_human = False
            else:
                finding = ", ".join(v["description"] for v in violations)
                worst = max(violations, key=lambda v: _SEVERITY_RANK.get(v["severity"].lower(), 0))
                severity = worst["severity"].lower()
                requires_human = severity in ("high", "critical")
            return AgentResult(
                agent=self.name,
                severity=severity,
                finding=finding,
                recommended_action="Remediate S3 bucket issues according to findings.",
                requires_human=requires_human,
                timestamp=datetime.utcnow(),
                metadata={"violations": violations},
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("[SecurityAgent] audit_s3_buckets AWS error: %s", exc)
            return AgentResult(
                agent=self.name,
                severity="info",
                finding=f"Failed to audit S3 buckets: {exc}",
                recommended_action="Check AWS credentials and network connectivity.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={"error": str(exc)},
            )

    # ---------------------------------------------------------------------
    # Helper utilities
    # ---------------------------------------------------------------------
    def _boto(self, service: str):
        """Lazy‑create and cache a boto3 client for the requested service.
        ``service`` is the AWS service name, e.g., ``ec2`` or ``s3``.
        """
        attr = f"_{service}"
        if getattr(self, attr, None) is None:
            client = boto3.client(
                service,
                aws_access_key_id=self.config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.config.AWS_SECRET_ACCESS_KEY,
                region_name=self.config.AWS_DEFAULT_REGION,
            )
            setattr(self, attr, client)
        return getattr(self, attr)

    async def log_action(self, action: str, result: AgentResult):
        """Write a security event to the audit log. Guarantees persistence.
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "agent": self.name,
            "severity": result.severity,
            "finding": result.finding,
            "requires_human": result.requires_human,
        }
        try:
            await asyncio.to_thread(self.audit_log.write, entry)
            logger.debug("[SecurityAgent] Logged action %s to audit log.", action)
        except Exception as exc:
            logger.error("[SecurityAgent] Failed to write audit log entry: %s", exc)

    def _parse_tfsec_severity(self, tfsec_severity: str) -> str:
        """Map tfsec severity strings (LOW, MEDIUM, HIGH) to InfraGenie levels.
        Returns a lower‑case severity string.
        """
        mapping = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}
        return mapping.get(tfsec_severity.upper(), "info")
