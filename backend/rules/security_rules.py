"""
Security Rules
Static rule definitions used by the SecurityAgent to validate Terraform
HCL and live AWS resource configurations against security best practices.
"""

SECURITY_RULES = [
    {
        "id": "SEC-001",
        "name": "No wildcard IAM actions",
        "severity": "critical",
        "description": "IAM policies must not use Action: '*' — grant least-privilege permissions only.",
        "hcl_pattern": r'"Action"\s*:\s*"\*"',
    },
    {
        "id": "SEC-002",
        "name": "S3 buckets must block public access",
        "severity": "high",
        "description": "All S3 buckets must have block_public_acls, block_public_policy, "
                       "ignore_public_acls, and restrict_public_buckets set to true.",
        "hcl_pattern": r'aws_s3_bucket(?!.*block_public_access)',
        "compliant_if_contains": "aws_s3_bucket_public_access_block",
    },
    {
        "id": "SEC-003",
        "name": "Encryption at rest required",
        "severity": "high",
        "description": "EBS volumes, RDS instances, and S3 buckets must enable server-side encryption.",
        "hcl_pattern": r'encrypted\s*=\s*false',
    },
    {
        "id": "SEC-004",
        "name": "Security groups must not allow unrestricted SSH",
        "severity": "critical",
        "description": "Port 22 must not be open to 0.0.0.0/0 or ::/0.",
        "hcl_pattern": r'from_port\s*=\s*22.*cidr_blocks\s*=\s*\["0\.0\.0\.0/0"\]',
    },
    {
        "id": "SEC-005",
        "name": "MFA delete on S3 versioning",
        "severity": "medium",
        "description": "S3 buckets holding sensitive data should enable MFA delete.",
        "hcl_pattern": r'mfa_delete\s*=\s*"Disabled"',
    },
]
