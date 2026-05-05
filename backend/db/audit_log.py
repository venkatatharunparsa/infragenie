"""
Audit Logger
Provides an async helper for writing structured audit log entries to the
database, recording every significant action taken by InfraGenie agents.
"""

import json
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .models import Base, AgentResultRecord


class AuditLogger:
    """Async audit logger backed by SQLAlchemy + aiosqlite."""

    def __init__(self, db_url: str = "sqlite+aiosqlite:///./infragenie.db"):
        self.engine = create_async_engine(db_url, echo=False)
        self.AsyncSessionLocal = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self):
        """Create all tables if they do not already exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def log(
        self,
        agent: str,
        severity: str,
        finding: str,
        recommended_action: str,
        requires_human: bool = False,
        proposed_tf: str = "",
        estimated_cost_delta: str = "$0.00",
        metadata: dict | None = None,
        request_id: int | None = None,
    ) -> AgentResultRecord:
        """
        Persist an audit log entry.

        Parameters
        ----------
        agent : str
            Name of the agent that produced this event.
        severity : str
            Severity level: info / low / medium / high / critical.
        finding : str
            Human-readable description of the event.
        recommended_action : str
            Suggested next step.
        requires_human : bool
            Whether human approval is needed.
        proposed_tf : str
            Associated Terraform HCL, if any.
        estimated_cost_delta : str
            Estimated cost impact string.
        metadata : dict, optional
            Extra structured data.
        request_id : int, optional
            Foreign key to infra_requests.id.

        Returns
        -------
        AgentResultRecord
            The persisted ORM record.
        """
        record = AgentResultRecord(
            request_id=request_id,
            agent=agent,
            severity=severity,
            finding=finding,
            recommended_action=recommended_action,
            requires_human=requires_human,
            proposed_tf=proposed_tf,
            estimated_cost_delta=estimated_cost_delta,
            timestamp=datetime.utcnow(),
            metadata_json=json.dumps(metadata or {}),
        )
        async with self.AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record
