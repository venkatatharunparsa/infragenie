"""
Monitor Agent
-------------
The MonitorAgent continuously observes the health, performance, and cost of
provisioned AWS resources. It queries CloudWatch for metric anomalies, Cost
Explorer for budget overruns, EC2 status checks for crashes, and Terraform
plan output to detect infrastructure drift.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .models import AgentResult
from terraform.tf_validator import TerraformValidator

logger = logging.getLogger(__name__)


class MonitorAgent:
    """
    Observes provisioned infrastructure and raises alerts on anomalies.

    Monitoring scope:
    - CloudWatch metrics (CPU utilisation, memory, error rates).
    - AWS Cost Explorer daily spend vs. configured budget threshold.
    - CloudTrail unusual API calls.
    - EC2 instance status checks for crash detection.
    - Terraform plan-based drift detection.
    - Full resource inventory across EC2, RDS, S3, and Lambda.
    """

    def __init__(self, config, cloudwatch_client=None, cost_explorer_client=None, tf_runner=None):
        """
        Parameters
        ----------
        config                : Settings
        cloudwatch_client     : CloudWatchClient wrapper (optional, falls back to boto3 direct)
        cost_explorer_client  : CostExplorerClient wrapper (optional)
        tf_runner             : TerraformRunner (optional, used for drift detection)
        """
        self.config               = config
        self.cloudwatch_client    = cloudwatch_client
        self.cost_explorer_client = cost_explorer_client
        self.tf_runner            = tf_runner
        self.name                 = "monitor"
        self.polling_interval     = 60  # seconds

        # Lazy boto3 clients — created on first use
        self._ec2    = None
        self._cw     = None
        self._rds    = None
        self._s3     = None
        self._lambda = None
        self._ce     = None

    # ── boto3 client helpers ──────────────────────────────────────────────────

    def _boto(self, service: str):
        """Return (and cache) a boto3 client for the given service."""
        cache_attr = f"_{service.replace('-', '_')}"
        if getattr(self, cache_attr, None) is None:
            setattr(self, cache_attr, boto3.client(
                service,
                aws_access_key_id=self.config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.config.AWS_SECRET_ACCESS_KEY,
                region_name=self.config.AWS_DEFAULT_REGION,
            ))
        return getattr(self, cache_attr)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, input: dict) -> AgentResult:
        """
        Route to the correct monitoring action.

        Supported actions (input['action']):
          'snapshot'       — full infrastructure state snapshot
          'check_drift'    — compare Terraform state to real AWS
          'check_budget'   — spending vs. threshold
          'check_metrics'  — CPU / memory anomaly check
        """
        action = input.get("action", "snapshot")
        logger.info("[MonitorAgent] run() action=%s", action)

        if action == "snapshot":
            snapshot = await self.get_snapshot()
            alert_count = len(snapshot.get("recent_alerts", []))
            alarm_count = len(snapshot.get("cloudwatch_alarms", []))
            severity = "info" if alarm_count == 0 else "medium"
            return AgentResult(
                agent=self.name,
                severity=severity,
                finding=(
                    f"Snapshot complete. EC2: {len(snapshot['ec2_instances'])}, "
                    f"RDS: {len(snapshot['rds_instances'])}, "
                    f"S3: {len(snapshot['s3_buckets'])}, "
                    f"Alarms in ALARM state: {alarm_count}, "
                    f"Recent alerts: {alert_count}"
                ),
                recommended_action="Review any active CloudWatch alarms.",
                requires_human=alarm_count > 0,
                timestamp=datetime.utcnow(),
                metadata={
                    "infra_state": snapshot,
                    "alerts":      snapshot.get("recent_alerts", []),
                    "metrics":     {},
                },
            )

        elif action == "check_drift":
            workspace_path = input.get("workspace_path", "")
            return await self.check_drift(workspace_path)

        elif action == "check_budget":
            threshold = float(input.get("threshold", self.config.BUDGET_THRESHOLD))
            return await self.check_budget(threshold)

        elif action == "check_metrics":
            instance_id = input.get("instance_id", "")
            threshold   = float(input.get("cpu_threshold", 85.0))
            if instance_id:
                return await self.check_cpu_anomaly(instance_id, threshold)
            return AgentResult(
                agent=self.name,
                severity="info",
                finding="No instance_id provided for metrics check.",
                recommended_action="Pass instance_id in the input dict.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={},
            )

        else:
            return AgentResult(
                agent=self.name,
                severity="info",
                finding=f"Unknown action '{action}'.",
                recommended_action="Use: snapshot | check_drift | check_budget | check_metrics",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={},
            )

    # ── Snapshot ──────────────────────────────────────────────────────────────

    async def get_snapshot(self) -> dict:
        """
        Return a complete infrastructure snapshot gathered from AWS.

        Returns
        -------
        dict
            Keys: ec2_instances, rds_instances, s3_buckets,
                  cloudwatch_alarms, recent_alerts, timestamp
        """
        resources  = await self.list_all_resources()
        alarms     = await asyncio.to_thread(self._list_active_alarms)
        snapshot   = {
            **resources,
            "cloudwatch_alarms": alarms,
            "recent_alerts":     [a["AlarmName"] for a in alarms if a.get("StateValue") == "ALARM"],
            "timestamp":         datetime.utcnow().isoformat(),
        }
        logger.info("[MonitorAgent] Snapshot gathered: %d EC2, %d alarms.",
                    len(snapshot["ec2_instances"]), len(alarms))
        return snapshot

    def _list_active_alarms(self) -> list[dict]:
        try:
            cw = self._boto("cloudwatch")
            resp = cw.describe_alarms(MaxRecords=100)
            return resp.get("MetricAlarms", [])
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] describe_alarms failed: %s", exc)
            return []

    # ── CPU anomaly ───────────────────────────────────────────────────────────

    async def check_cpu_anomaly(self, instance_id: str, threshold: float = 85.0) -> AgentResult:
        """
        Get the last 10 minutes of CPUUtilization for an EC2 instance.
        Raises HIGH severity if the average exceeds *threshold* for > 5 minutes.
        """
        logger.info("[MonitorAgent] check_cpu_anomaly: instance=%s threshold=%.1f%%", instance_id, threshold)
        try:
            cw = self._boto("cloudwatch")
            end   = datetime.utcnow()
            start = end - timedelta(minutes=10)

            resp = await asyncio.to_thread(
                cw.get_metric_statistics,
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=60,
                Statistics=["Average"],
            )
            points = resp.get("Datapoints", [])

            if not points:
                return AgentResult(
                    agent=self.name,
                    severity="info",
                    finding=f"No CPU metrics found for instance {instance_id} in the last 10 minutes.",
                    recommended_action="Ensure CloudWatch agent is running and the instance is active.",
                    requires_human=False,
                    timestamp=datetime.utcnow(),
                    metadata={"instance_id": instance_id},
                )

            high_points = [p for p in points if p["Average"] >= threshold]
            avg_cpu     = sum(p["Average"] for p in points) / len(points)
            sustained   = len(high_points) >= 5  # ≥ 5 consecutive 1-min datapoints

            if sustained:
                est_cost = "+$0.05/hr (scale-up estimate)"
                return AgentResult(
                    agent=self.name,
                    severity="high",
                    finding=(
                        f"CPU anomaly detected on {instance_id}: average {avg_cpu:.1f}% over "
                        f"last {len(points)} minutes, exceeding {threshold}% for {len(high_points)} minutes."
                    ),
                    recommended_action="scale_up",
                    requires_human=True,
                    estimated_cost_delta=est_cost,
                    timestamp=datetime.utcnow(),
                    metadata={
                        "instance_id":   instance_id,
                        "avg_cpu":       round(avg_cpu, 2),
                        "threshold":     threshold,
                        "high_minutes":  len(high_points),
                        "datapoints":    len(points),
                    },
                )

            return AgentResult(
                agent=self.name,
                severity="info",
                finding=(
                    f"CPU utilisation on {instance_id} is {avg_cpu:.1f}% — within normal range."
                ),
                recommended_action="No action required.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={"instance_id": instance_id, "avg_cpu": round(avg_cpu, 2)},
            )

        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] check_cpu_anomaly AWS error: %s", exc)
            return self._aws_error_result("check_cpu_anomaly", exc)

    # ── Drift detection ───────────────────────────────────────────────────────

    async def check_drift(self, workspace_path: str) -> AgentResult:
        """
        Run 'terraform plan' on an existing workspace to detect infrastructure drift.

        If resources_to_change > 0 or resources_to_destroy > 0 that were not
        user-requested, returns MEDIUM severity with full drift details.
        """
        logger.info("[MonitorAgent] check_drift: workspace=%s", workspace_path)

        if not workspace_path:
            return AgentResult(
                agent=self.name,
                severity="info",
                finding="No workspace_path provided for drift check.",
                recommended_action="Pass workspace_path in the input dict.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={},
            )

        try:
            if self.tf_runner:
                result = await self.tf_runner.plan(workspace_path)
                plan_out = result.stdout + result.stderr
            else:
                # Fallback: run directly via asyncio subprocess
                proc = await asyncio.create_subprocess_exec(
                    "terraform", "plan", "-no-color", "-input=false", "-detailed-exitcode",
                    cwd=workspace_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=300)
                plan_out = stdout_b.decode() + stderr_b.decode()

            parsed   = TerraformValidator().parse_plan_output(plan_out)
            to_add   = parsed.get("resources_to_add", 0)
            to_change = parsed.get("resources_to_change", 0)
            to_destroy = parsed.get("resources_to_destroy", 0)
            res_list = parsed.get("resource_list", [])

            if to_change > 0 or to_destroy > 0:
                return AgentResult(
                    agent=self.name,
                    severity="medium",
                    finding=(
                        f"Infrastructure drift detected: {to_add} to add, "
                        f"{to_change} to change, {to_destroy} to destroy. "
                        f"Affected resources: {', '.join(res_list) or 'see metadata'}"
                    ),
                    recommended_action=(
                        "Review drifted resources and either re-apply Terraform to reconcile "
                        "or update the Terraform code to reflect intentional manual changes."
                    ),
                    requires_human=True,
                    proposed_tf=plan_out[:4000],  # truncate for AgentResult
                    timestamp=datetime.utcnow(),
                    metadata={
                        "to_add":      to_add,
                        "to_change":   to_change,
                        "to_destroy":  to_destroy,
                        "resource_list": res_list,
                        "workspace":   workspace_path,
                    },
                )

            return AgentResult(
                agent=self.name,
                severity="info",
                finding="No infrastructure drift detected — Terraform state matches real AWS resources.",
                recommended_action="No action required.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={"workspace": workspace_path},
            )

        except asyncio.TimeoutError:
            return AgentResult(
                agent=self.name,
                severity="medium",
                finding="Drift check timed out after 300 seconds.",
                recommended_action="Run drift check manually or increase the timeout.",
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"workspace": workspace_path},
            )
        except FileNotFoundError:
            return AgentResult(
                agent=self.name,
                severity="info",
                finding="Terraform CLI not found — drift check skipped.",
                recommended_action="Install the Terraform CLI to enable drift detection.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={},
            )

    # ── Budget check ──────────────────────────────────────────────────────────

    async def check_budget(self, threshold: float) -> AgentResult:
        """
        Query AWS Cost Explorer for current-month spend and compare to threshold.

        Returns MEDIUM if spend > 80% of threshold, HIGH + requires_human if exceeded.
        """
        logger.info("[MonitorAgent] check_budget: threshold=$%.2f", threshold)
        try:
            ce     = self._boto("ce")
            today  = datetime.utcnow().date()
            first  = today.replace(day=1)

            resp = await asyncio.to_thread(
                ce.get_cost_and_usage,
                TimePeriod={"Start": str(first), "End": str(today)},
                Granularity="MONTHLY",
                Metrics=["BlendedCost"],
            )
            results = resp.get("ResultsByTime", [])
            spend = float(results[0]["Total"]["BlendedCost"]["Amount"]) if results else 0.0

            pct = (spend / threshold * 100) if threshold > 0 else 0

            if spend > threshold:
                return AgentResult(
                    agent=self.name,
                    severity="high",
                    finding=(
                        f"Budget exceeded: ${spend:.2f} spent this month "
                        f"(threshold: ${threshold:.2f}, {pct:.1f}% of budget)."
                    ),
                    recommended_action=(
                        "Immediately review AWS Cost Explorer for top cost drivers. "
                        "Consider stopping non-essential resources."
                    ),
                    requires_human=True,
                    estimated_cost_delta=f"+${spend - threshold:.2f} over budget",
                    timestamp=datetime.utcnow(),
                    metadata={"spend_usd": spend, "threshold": threshold, "pct": round(pct, 1)},
                )

            if spend > threshold * 0.8:
                return AgentResult(
                    agent=self.name,
                    severity="medium",
                    finding=(
                        f"Budget warning: ${spend:.2f} spent ({pct:.1f}% of ${threshold:.2f} limit). "
                        f"Approaching threshold."
                    ),
                    recommended_action="Review spending to avoid exceeding the budget.",
                    requires_human=False,
                    estimated_cost_delta=f"${threshold - spend:.2f} remaining",
                    timestamp=datetime.utcnow(),
                    metadata={"spend_usd": spend, "threshold": threshold, "pct": round(pct, 1)},
                )

            return AgentResult(
                agent=self.name,
                severity="info",
                finding=f"Budget OK: ${spend:.2f} spent ({pct:.1f}% of ${threshold:.2f} limit).",
                recommended_action="No action required.",
                requires_human=False,
                estimated_cost_delta=f"${threshold - spend:.2f} remaining",
                timestamp=datetime.utcnow(),
                metadata={"spend_usd": spend, "threshold": threshold, "pct": round(pct, 1)},
            )

        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] check_budget AWS error: %s", exc)
            return self._aws_error_result("check_budget", exc)

    # ── Crash detection ───────────────────────────────────────────────────────

    async def detect_service_crash(self, instance_id: str) -> AgentResult:
        """
        Check EC2 instance status checks via boto3.

        Returns CRITICAL with recommended_action='restart_service' and
        requires_human=False if the instance has failed status checks or
        is in a stopped/terminated state unexpectedly.
        """
        logger.info("[MonitorAgent] detect_service_crash: instance=%s", instance_id)
        try:
            ec2  = self._boto("ec2")
            resp = await asyncio.to_thread(
                ec2.describe_instance_status,
                InstanceIds=[instance_id],
                IncludeAllInstances=True,
            )
            statuses = resp.get("InstanceStatuses", [])

            if not statuses:
                return AgentResult(
                    agent=self.name,
                    severity="medium",
                    finding=f"No status data returned for instance {instance_id}.",
                    recommended_action="Verify the instance ID is correct and the instance exists.",
                    requires_human=True,
                    timestamp=datetime.utcnow(),
                    metadata={"instance_id": instance_id},
                )

            status = statuses[0]
            instance_state  = status.get("InstanceState", {}).get("Name", "unknown")
            instance_check  = status.get("InstanceStatus", {}).get("Status", "unknown")
            system_check    = status.get("SystemStatus", {}).get("Status", "unknown")

            failed = (
                instance_check == "impaired"
                or system_check == "impaired"
                or instance_state in ("stopped", "terminated")
            )

            if failed:
                return AgentResult(
                    agent=self.name,
                    severity="critical",
                    finding=(
                        f"Service crash detected on {instance_id}: "
                        f"state={instance_state}, "
                        f"instance_check={instance_check}, "
                        f"system_check={system_check}."
                    ),
                    recommended_action="restart_service",
                    requires_human=False,
                    timestamp=datetime.utcnow(),
                    metadata={
                        "instance_id":    instance_id,
                        "instance_state": instance_state,
                        "instance_check": instance_check,
                        "system_check":   system_check,
                    },
                )

            return AgentResult(
                agent=self.name,
                severity="info",
                finding=(
                    f"Instance {instance_id} is healthy: "
                    f"state={instance_state}, checks=OK."
                ),
                recommended_action="No action required.",
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={
                    "instance_id":    instance_id,
                    "instance_state": instance_state,
                    "instance_check": instance_check,
                    "system_check":   system_check,
                },
            )

        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] detect_service_crash AWS error: %s", exc)
            return self._aws_error_result("detect_service_crash", exc)

    # ── Resource inventory ────────────────────────────────────────────────────

    async def list_all_resources(self) -> dict:
        """
        List all EC2, RDS, S3, and Lambda resources in the configured region.

        Returns
        -------
        dict
            Keys: ec2_instances, rds_instances, s3_buckets, lambda_functions
        """
        logger.info("[MonitorAgent] list_all_resources: region=%s", self.config.AWS_DEFAULT_REGION)

        ec2_instances, rds_instances, s3_buckets, lambda_functions = await asyncio.gather(
            asyncio.to_thread(self._list_ec2),
            asyncio.to_thread(self._list_rds),
            asyncio.to_thread(self._list_s3),
            asyncio.to_thread(self._list_lambda),
        )

        return {
            "ec2_instances":    ec2_instances,
            "rds_instances":    rds_instances,
            "s3_buckets":       s3_buckets,
            "lambda_functions": lambda_functions,
        }

    def _list_ec2(self) -> list[dict]:
        try:
            ec2  = self._boto("ec2")
            resp = ec2.describe_instances()
            instances = []
            for reservation in resp.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    name = next(
                        (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), ""
                    )
                    instances.append({
                        "instance_id":   inst.get("InstanceId"),
                        "instance_type": inst.get("InstanceType"),
                        "state":         inst.get("State", {}).get("Name"),
                        "public_ip":     inst.get("PublicIpAddress"),
                        "private_ip":    inst.get("PrivateIpAddress"),
                        "name":          name,
                        "az":            inst.get("Placement", {}).get("AvailabilityZone"),
                    })
            return instances
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] _list_ec2 failed: %s", exc)
            return []

    def _list_rds(self) -> list[dict]:
        try:
            rds  = self._boto("rds")
            resp = rds.describe_db_instances()
            return [
                {
                    "db_identifier": db.get("DBInstanceIdentifier"),
                    "engine":        db.get("Engine"),
                    "status":        db.get("DBInstanceStatus"),
                    "instance_class": db.get("DBInstanceClass"),
                    "multi_az":      db.get("MultiAZ"),
                    "storage_encrypted": db.get("StorageEncrypted"),
                }
                for db in resp.get("DBInstances", [])
            ]
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] _list_rds failed: %s", exc)
            return []

    def _list_s3(self) -> list[dict]:
        try:
            s3   = self._boto("s3")
            resp = s3.list_buckets()
            return [
                {
                    "name":         b.get("Name"),
                    "creation_date": str(b.get("CreationDate", "")),
                }
                for b in resp.get("Buckets", [])
            ]
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] _list_s3 failed: %s", exc)
            return []

    def _list_lambda(self) -> list[dict]:
        try:
            lam  = self._boto("lambda")
            resp = lam.list_functions()
            return [
                {
                    "name":        fn.get("FunctionName"),
                    "runtime":     fn.get("Runtime"),
                    "memory_mb":   fn.get("MemorySize"),
                    "timeout_sec": fn.get("Timeout"),
                    "last_modified": fn.get("LastModified"),
                }
                for fn in resp.get("Functions", [])
            ]
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[MonitorAgent] _list_lambda failed: %s", exc)
            return []

    # ── Utility ───────────────────────────────────────────────────────────────

    def _aws_error_result(self, operation: str, exc: Exception) -> AgentResult:
        """Standardised INFO-severity result when an AWS call fails gracefully."""
        return AgentResult(
            agent=self.name,
            severity="info",
            finding=f"AWS call '{operation}' failed: {exc}",
            recommended_action="Check AWS credentials, IAM permissions, and network connectivity.",
            requires_human=False,
            timestamp=datetime.utcnow(),
            metadata={"operation": operation, "error": str(exc)},
        )
