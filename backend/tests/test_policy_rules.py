from __future__ import annotations

from backend.rules.policy_rules import PolicyRulesEngine


def test_exceeds_budget(policy_engine: PolicyRulesEngine) -> None:
    decision = policy_engine.check_request(
        user_input="create infrastructure",
        proposed_resources=["aws_s3_bucket"],
        estimated_cost=11.0,
        budget_threshold=10.0,
    )

    assert decision.tier == 4
    assert decision.requires_human is True


def test_destroy_requires_human(policy_engine: PolicyRulesEngine) -> None:
    decision = policy_engine.check_request(
        user_input="destroy the database",
        proposed_resources=["aws_s3_bucket"],
        estimated_cost=0.0,
        budget_threshold=10.0,
    )

    assert decision.tier == 4
    assert decision.requires_human is True


def test_free_tier_safe(policy_engine: PolicyRulesEngine) -> None:
    decision = policy_engine.check_request(
        user_input="create a small demo",
        proposed_resources=["aws_s3_bucket", "aws_lambda_function"],
        estimated_cost=0.0,
        budget_threshold=10.0,
    )

    assert decision.tier == 2
    assert decision.requires_human is False
