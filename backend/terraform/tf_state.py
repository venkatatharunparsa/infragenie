"""
Terraform State Manager
Provides helpers for reading, refreshing, and listing resources in the
Terraform remote state stored in an S3 bucket with a DynamoDB lock table.
"""

import json
import boto3


class TerraformState:
    """Interacts with Terraform remote state in S3."""

    def __init__(self, config):
        self.config = config
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )
        self.bucket = config.TERRAFORM_STATE_BUCKET

    def get_state(self, key: str = "infragenie/terraform.tfstate") -> dict:
        """
        Download and parse the Terraform state file from S3.

        Parameters
        ----------
        key : str
            S3 object key for the state file.

        Returns
        -------
        dict
            Parsed Terraform state as a Python dictionary.
        """
        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        raw = response["Body"].read().decode("utf-8")
        return json.loads(raw)

    def list_resources(self, key: str = "infragenie/terraform.tfstate") -> list[dict]:
        """
        Return a flat list of all managed resources from the state file.

        Returns
        -------
        list[dict]
            Each item contains ``type``, ``name``, and ``provider`` fields.
        """
        state = self.get_state(key)
        resources = []
        for resource in state.get("resources", []):
            resources.append({
                "type": resource.get("type"),
                "name": resource.get("name"),
                "provider": resource.get("provider"),
            })
        return resources
