from __future__ import annotations

from backend.agents.types import AgentResult


def test_requires_immediate_action_critical() -> None:
    result = AgentResult(
        agent="security",
        severity="CRITICAL",
        finding="Open SSH detected",
        recommended_action="Block deployment",
        requires_human=True,
    )

    assert result.requires_immediate_action() is True


def test_requires_immediate_action_low() -> None:
    result = AgentResult(
        agent="monitor",
        severity="LOW",
        finding="Missing tags",
        recommended_action="Add default tags",
        requires_human=False,
    )

    assert result.requires_immediate_action() is False


def test_to_dict_complete(agent_result: AgentResult) -> None:
    data = agent_result.to_dict()

    assert set(data) == {
        "agent",
        "severity",
        "finding",
        "recommended_action",
        "requires_human",
        "proposed_tf",
        "estimated_cost_delta",
        "timestamp",
        "metadata",
    }


def test_default_values() -> None:
    result = AgentResult(
        agent="planner",
        severity="INFO",
        finding="Plan generated",
        recommended_action="Review plan",
        requires_human=False,
    )

    assert result.proposed_tf == ""
    assert result.estimated_cost_delta == "$0"
