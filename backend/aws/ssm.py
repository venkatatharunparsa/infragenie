"""
AWS Systems Manager (SSM) Client
Provides parameter retrieval, command execution via Run Command, and
session management helpers used by the ExecutorAgent.
"""

import boto3


class SSMClient:
    """Wrapper around boto3 SSM for parameter store and Run Command."""

    def __init__(self, config):
        self.client = boto3.client(
            "ssm",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_DEFAULT_REGION,
        )

    def get_parameter(self, name: str, with_decryption: bool = True) -> str:
        """
        Retrieve a single SSM parameter value.

        Parameters
        ----------
        name : str
            Full parameter path, e.g. ``"/infragenie/prod/db_password"``.
        with_decryption : bool
            Decrypt SecureString parameters (default True).

        Returns
        -------
        str
            The parameter value.
        """
        response = self.client.get_parameter(Name=name, WithDecryption=with_decryption)
        return response["Parameter"]["Value"]

    def put_parameter(self, name: str, value: str, param_type: str = "SecureString", overwrite: bool = True):
        """
        Create or update an SSM parameter.

        Parameters
        ----------
        name : str
            Parameter path.
        value : str
            Parameter value.
        param_type : str
            ``"String"``, ``"StringList"``, or ``"SecureString"``.
        overwrite : bool
            Whether to overwrite an existing parameter (default True).
        """
        self.client.put_parameter(
            Name=name,
            Value=value,
            Type=param_type,
            Overwrite=overwrite,
        )

    def send_command(self, instance_ids: list[str], commands: list[str]) -> str:
        """
        Send a Run Command document to EC2 instances.

        Parameters
        ----------
        instance_ids : list[str]
            Target EC2 instance IDs.
        commands : list[str]
            Shell commands to execute on each instance.

        Returns
        -------
        str
            The SSM Command ID for status tracking.
        """
        response = self.client.send_command(
            InstanceIds=instance_ids,
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands},
        )
        return response["Command"]["CommandId"]
