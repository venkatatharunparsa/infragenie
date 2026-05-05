"""
Amazon CloudWatch Client
Wraps boto3 CloudWatch calls for metric retrieval, alarm management,
and log group queries used by the MonitorAgent.
"""

import boto3
from datetime import datetime, timedelta


class CloudWatchClient:
    """Thin wrapper around boto3 CloudWatch for InfraGenie monitoring."""

    def __init__(self, config):
        self.client = boto3.client(
            "cloudwatch",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )
        self.logs = boto3.client(
            "logs",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )

    def get_metric_statistics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: list[dict],
        period: int = 300,
        hours: int = 1,
        statistic: str = "Average",
    ) -> list[dict]:
        """
        Retrieve CloudWatch metric statistics for the past *hours* hours.

        Parameters
        ----------
        namespace : str
            AWS namespace, e.g. ``"AWS/EC2"``.
        metric_name : str
            Metric name, e.g. ``"CPUUtilization"``.
        dimensions : list[dict]
            List of ``{"Name": ..., "Value": ...}`` dimension filters.
        period : int
            Granularity in seconds (default 5 minutes).
        hours : int
            Look-back window in hours (default 1 hour).
        statistic : str
            Statistic type: Average, Sum, Maximum, Minimum, SampleCount.

        Returns
        -------
        list[dict]
            List of datapoint dicts from CloudWatch.
        """
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        response = self.client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=[statistic],
        )
        return response.get("Datapoints", [])

    def list_alarms(self, state: str = "ALARM") -> list[dict]:
        """Return all CloudWatch alarms in the given state."""
        response = self.client.describe_alarms(StateValue=state)
        return response.get("MetricAlarms", [])
