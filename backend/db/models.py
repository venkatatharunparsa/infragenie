"""
Database Models
SQLAlchemy ORM models for InfraGenie persistent storage.
Uses aiosqlite for async SQLite access (swappable for Postgres via DB_URL).
"""

import json
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class InfraRequest(Base):
    """Stores user infrastructure requests and their lifecycle status."""

    __tablename__ = "infra_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=True, index=True)
    request_text = Column(Text, nullable=False)
    status = Column(String(32), default="pending")          # pending | planning | approved | executing | done | failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    proposed_tf = Column(Text, nullable=True)
    estimated_cost_delta = Column(String(32), nullable=True)
    approved_by = Column(String(128), nullable=True)
    approved_at = Column(DateTime, nullable=True)


class AgentResultRecord(Base):
    """Persists every AgentResult emitted during a request's lifecycle."""

    __tablename__ = "agent_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, nullable=True, index=True)
    agent = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    finding = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    requires_human = Column(Boolean, default=False)
    proposed_tf = Column(Text, nullable=True)
    estimated_cost_delta = Column(String(32), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(Text, default="{}")

    @property
    def metadata_dict(self) -> dict:
        return json.loads(self.metadata_json or "{}")

    @metadata_dict.setter
    def metadata_dict(self, value: dict):
        self.metadata_json = json.dumps(value)
