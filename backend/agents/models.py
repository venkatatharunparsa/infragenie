"""
Agent Data Models
Shared dataclasses and types used by all InfraGenie agents.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentResult:
    """
    Standardised result returned by every InfraGenie agent.

    Attributes
    ----------
    agent : str
        Name / identifier of the agent that produced this result.
    severity : str
        Severity level of the finding: "info", "low", "medium", "high", "critical".
    finding : str
        Human-readable description of what the agent discovered or decided.
    recommended_action : str
        The action InfraGenie recommends taking based on this finding.
    requires_human : bool
        Whether the recommended action requires explicit human approval before
        execution (e.g. destructive changes, high-cost operations).
    proposed_tf : str
        Optional Terraform HCL snippet that would implement the recommendation.
    estimated_cost_delta : str
        Estimated change in monthly AWS cost, e.g. "+$12.50/mo" or "-$5.00/mo".
    timestamp : datetime
        UTC timestamp of when this result was created.
    metadata : dict
        Arbitrary key-value pairs carrying agent-specific extra data.
    """

    agent: str
    severity: str
    finding: str
    recommended_action: str
    requires_human: bool
    proposed_tf: str = ""
    estimated_cost_delta: str = "$0.00"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
