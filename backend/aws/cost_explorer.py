"""
AWS Cost Explorer Client
Retrieves current and forecast spend data to support budget-threshold
enforcement by the OrchestratorAgent and PlannerAgent.
"""

import boto3
from datetime import datetime, timedelta


class CostExplorerClient:
    """Wrapper around boto3 Cost Explorer for spend analysis."""

    def __init__(self, config):
        # Cost Explorer is a global service — always us-east-1
        self.client = boto3.client(
            "ce",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name="us-east-1",
        )
        self.budget_threshold = float(config.BUDGET_THRESHOLD)

    def get_monthly_cost(self) -> float:
        """
        Return the total AWS spend for the current calendar month (USD).

        Returns
        -------
        float
            Total blended cost in USD.
        """
        today = datetime.utcnow().date()
        first = today.replace(day=1)
        response = self.client.get_cost_and_usage(
            TimePeriod={"Start": str(first), "End": str(today)},
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
        )
        results = response.get("ResultsByTime", [])
        if not results:
            return 0.0
        amount = results[0]["Total"]["BlendedCost"]["Amount"]
        return float(amount)

    def is_over_budget(self) -> bool:
        """Return True if current monthly spend exceeds BUDGET_THRESHOLD."""
        return self.get_monthly_cost() >= self.budget_threshold

    def get_service_breakdown(self) -> list[dict]:
        """
        Return cost breakdown by AWS service for the current month.

        Returns
        -------
        list[dict]
            Each item has ``service`` and ``cost_usd`` keys.
        """
        today = datetime.utcnow().date()
        first = today.replace(day=1)
        response = self.client.get_cost_and_usage(
            TimePeriod={"Start": str(first), "End": str(today)},
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        breakdown = []
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                breakdown.append({
                    "service": group["Keys"][0],
                    "cost_usd": float(group["Metrics"]["BlendedCost"]["Amount"]),
                })
        return sorted(breakdown, key=lambda x: x["cost_usd"], reverse=True)
