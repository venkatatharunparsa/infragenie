from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

from backend.terraform.tf_runner import TerraformRunner


def test_init_command(terraform_runner: TerraformRunner) -> None:
    with patch("backend.terraform.tf_runner.subprocess.run") as run_mock:
        run_mock.return_value = CompletedProcess(
            args=["terraform", "init"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        terraform_runner.init()

    run_mock.assert_called_once()
    assert run_mock.call_args.args[0] == ["terraform", "init"]


def test_apply_command(terraform_runner: TerraformRunner) -> None:
    with patch("backend.terraform.tf_runner.subprocess.run") as run_mock:
        run_mock.return_value = CompletedProcess(
            args=["terraform", "apply", "-auto-approve"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        terraform_runner.apply()

    assert "-auto-approve" in run_mock.call_args.args[0]


def test_result_on_success(terraform_runner: TerraformRunner) -> None:
    with patch("backend.terraform.tf_runner.subprocess.run") as run_mock:
        run_mock.return_value = CompletedProcess(
            args=["terraform", "init"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        result = terraform_runner.init()

    assert result.exit_code == 0
    assert result.success is True


def test_result_on_failure(terraform_runner: TerraformRunner) -> None:
    with patch("backend.terraform.tf_runner.subprocess.run") as run_mock:
        run_mock.return_value = CompletedProcess(
            args=["terraform", "init"],
            returncode=1,
            stdout="",
            stderr="failed",
        )

        result = terraform_runner.init()

    assert result.exit_code == 1
    assert result.success is False
