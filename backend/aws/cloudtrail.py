"""
AWS CloudTrail Client
Queries CloudTrail event history for audit, security anomaly detection,
and compliance reporting used by the SecurityAgent and MonitorAgent.
"""

import boto3
from datetime import datetime, timedelta


class CloudTrailClient:
    """Wrapper around boto3 CloudTrail for event lookup and analysis."""

    def __init__(self, config):
        self.client = boto3.client(
            "cloudtrail",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )

    def lookup_events(
        self,
        hours: int = 24,
        attribute_key: str | None = None,
        attribute_value: str | None = None,
        max_results: int = 50,
    ) -> list[dict]:
        """
        Retrieve CloudTrail events from the past *hours* hours.

        Parameters
        ----------
        hours : int
            Look-back window (default 24 hours).
        attribute_key : str, optional
            Filter attribute key (e.g. ``"EventName"``, ``"Username"``).
        attribute_value : str, optional
            Filter attribute value.
        max_results : int
            Maximum number of events to return (default 50).

        Returns
        -------
        list[dict]
            List of CloudTrail event dictionaries.
        """
        kwargs: dict = {
            "StartTime": datetime.utcnow() - timedelta(hours=hours),
            "EndTime": datetime.utcnow(),
            "MaxResults": max_results,
        }
        if attribute_key and attribute_value:
            kwargs["LookupAttributes"] = [
                {"AttributeKey": attribute_key, "AttributeValue": attribute_value}
            ]
        response = self.client.lookup_events(**kwargs)
        return response.get("Events", [])

    def get_sensitive_events(self, hours: int = 24) -> list[dict]:
        """
        Return a filtered list of high-risk API calls (IAM, root logins,
        security-group mutations) from the past *hours* hours.
        """
        sensitive_actions = {
            "DeleteBucket", "DeleteDBInstance", "DeleteSecurityGroup",
            "AttachRolePolicy", "CreateAccessKey", "ConsoleLogin",
            "StopInstances", "TerminateInstances", "DeleteTrail",
        }
        events = self.lookup_events(hours=hours, max_results=200)
        return [e for e in events if e.get("EventName") in sensitive_actions]
