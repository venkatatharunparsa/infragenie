from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.types import AgentResult
from backend.rules.policy_rules import PolicyRulesEngine
from backend.rules.security_rules import RuleViolation, SecurityRulesEngine
from backend.terraform.tf_runner import TerraformRunner


@pytest.fixture
def security_engine() -> SecurityRulesEngine:
    return SecurityRulesEngine()


@pytest.fixture
def policy_engine() -> PolicyRulesEngine:
    return PolicyRulesEngine()


@pytest.fixture
def critical_violation() -> RuleViolation:
    return RuleViolation(
        rule_id="RULE-001",
        severity="CRITICAL",
        description="Port 22 is open to the internet.",
        line_number=4,
        auto_fixable=True,
        fix_suggestion="Restrict CIDR range.",
    )


@pytest.fixture
def low_violation() -> RuleViolation:
    return RuleViolation(
        rule_id="RULE-009",
        severity="LOW",
        description="Resource is missing tags.",
        line_number=1,
        auto_fixable=True,
        fix_suggestion="Add tags.",
    )


@pytest.fixture
def agent_result() -> AgentResult:
    return AgentResult(
        agent="security",
        severity="LOW",
        finding="No blockers found",
        recommended_action="Proceed",
        requires_human=False,
    )


@pytest.fixture
def terraform_runner() -> TerraformRunner:
    return TerraformRunner(str(Path(__file__).resolve().parent))


@pytest.fixture
def mock_boto3_session():
    with patch("backend.aws.cloudwatch.boto3.Session") as session_mock:
        session = MagicMock()
        session_mock.return_value = session
        yield session_mock
