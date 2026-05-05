from __future__ import annotations

from backend.rules.security_rules import RuleViolation, SecurityRulesEngine


def test_detects_open_port_22(security_engine: SecurityRulesEngine) -> None:
    tf_code = """
resource "aws_security_group" "ssh" {
  ingress {
    from_port = 22
    to_port = 22
    cidr_blocks = ["0.0.0.0/0"]
  }
}
"""

    violations = security_engine.check(tf_code)

    assert any(
        violation.rule_id == "RULE-001" and violation.severity == "CRITICAL"
        for violation in violations
    )


def test_detects_public_s3(security_engine: SecurityRulesEngine) -> None:
    tf_code = """
resource "aws_s3_bucket" "public" {
  bucket = "demo"
  acl = "public-read"
  versioning {
    enabled = true
  }
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  tags = {
    ManagedBy = "InfraGenie"
  }
}
"""

    violations = security_engine.check(tf_code)

    assert any(
        violation.rule_id == "RULE-003" and violation.severity == "CRITICAL"
        for violation in violations
    )


def test_clean_code_passes(security_engine: SecurityRulesEngine) -> None:
    tf_code = """
resource "aws_s3_bucket" "safe" {
  bucket = "demo"
  acl = "private"
  versioning {
    enabled = true
  }
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  tags = {
    ManagedBy = "InfraGenie"
  }
}
"""

    violations = security_engine.check(tf_code)

    assert violations == []


def test_auto_fix_works(security_engine: SecurityRulesEngine) -> None:
    tf_code = """
resource "aws_s3_bucket" "public" {
  bucket = "demo"
  acl = "public-read"
}
"""
    violations = security_engine.check(tf_code)

    fixed_code = security_engine.auto_fix(tf_code, violations)

    assert 'acl = "private"' in fixed_code
    assert "versioning" in fixed_code
    assert "server_side_encryption_configuration" in fixed_code
    assert "tags" in fixed_code


def test_has_blockers_true(
    security_engine: SecurityRulesEngine, critical_violation: RuleViolation
) -> None:
    assert security_engine.has_blockers([critical_violation]) is True


def test_has_blockers_false(
    security_engine: SecurityRulesEngine, low_violation: RuleViolation
) -> None:
    assert security_engine.has_blockers([low_violation]) is False
