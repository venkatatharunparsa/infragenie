"""
InfraGenie Configuration
Centralised environment-variable loading via Pydantic BaseSettings.
All secrets and runtime configuration are read from the .env file (or
actual environment variables) at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # AI / LLM
    # ------------------------------------------------------------------ #
    GEMINI_API_KEY: str = ""
    GEMINI_FALLBACK_API_KEY: str = ""

    # ------------------------------------------------------------------ #
    # AWS credentials & region
    # ------------------------------------------------------------------ #
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_DEFAULT_REGION: str = "us-east-1"

    # ------------------------------------------------------------------ #
    # Application secrets
    # ------------------------------------------------------------------ #
    INFRAGENIE_SECRET: str = "change-me-in-production"

    # ------------------------------------------------------------------ #
    # Cost management
    # ------------------------------------------------------------------ #
    BUDGET_THRESHOLD: float = 500.0  # USD

    # ------------------------------------------------------------------ #
    # Terraform remote-state (S3 + DynamoDB)
    # ------------------------------------------------------------------ #
    TERRAFORM_STATE_BUCKET: str = ""
    TERRAFORM_LOCK_TABLE: str = ""

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    DB_URL: str = "sqlite+aiosqlite:///./infragenie.db"

    # ------------------------------------------------------------------ #
    # ChromaDB vector store
    # ------------------------------------------------------------------ #
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # ------------------------------------------------------------------ #
    # Terraform workspace
    # ------------------------------------------------------------------ #
    TERRAFORM_WORKSPACE_DIR: str = "./terraform_workspace"
