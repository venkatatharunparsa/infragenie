"""
Policy Rules
Organisational and compliance policies enforced by the OrchestratorAgent
before any infrastructure change is approved for execution.
"""

POLICY_RULES = [
    {
        "id": "POL-001",
        "name": "Budget threshold enforcement",
        "description": "Reject any plan whose estimated_cost_delta exceeds BUDGET_THRESHOLD.",
        "action": "block",
    },
    {
        "id": "POL-002",
        "name": "Approved AWS regions only",
        "description": "Resources may only be provisioned in pre-approved AWS regions.",
        "approved_regions": ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"],
        "action": "block",
    },
    {
        "id": "POL-003",
        "name": "Mandatory resource tagging",
        "description": "All AWS resources must carry Environment, Owner, and CostCenter tags.",
        "required_tags": ["Environment", "Owner", "CostCenter"],
        "action": "warn",
    },
    {
        "id": "POL-004",
        "name": "Production changes require human approval",
        "description": "Any change targeting the 'production' environment must be manually approved.",
        "action": "require_human",
    },
    {
        "id": "POL-005",
        "name": "No resource deletion without backup",
        "description": "Destructive Terraform operations (destroy / replace) on stateful resources "
                       "require a verified snapshot or backup before proceeding.",
        "action": "require_human",
    },
]
