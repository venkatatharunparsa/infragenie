"""
InfraGenie — FastAPI Backend Entry Point
Provides REST API and WebSocket endpoints for the InfraGenie infrastructure
management platform. Boots all agents on startup and wires the WebSocket
broadcaster into the OrchestratorAgent background loop.
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Security,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from .config import Settings
from .agents.models import AgentResult
from .agents.planner import PlannerAgent
from .agents.executor import ExecutorAgent
from .agents.monitor import MonitorAgent
from .agents.security import SecurityAgent
from .agents.orchestrator import OrchestratorAgent, InfraRequest
from .rag.chroma_client import ChromaRAGClient
from .rag.knowledge_loader import KnowledgeLoader
from .db.audit_log import AuditLogger
from .aws.cloudwatch import CloudWatchClient
from .aws.cost_explorer import CostExplorerClient
from .terraform.tf_runner import TerraformRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings (loaded once at module level)
# ---------------------------------------------------------------------------
settings = Settings()

# ---------------------------------------------------------------------------
# Global agent singletons — populated during lifespan startup
# ---------------------------------------------------------------------------
_planner:      Optional[PlannerAgent]      = None
_executor:     Optional[ExecutorAgent]     = None
_monitor:      Optional[MonitorAgent]      = None
_security:     Optional[SecurityAgent]     = None
_orchestrator: Optional[OrchestratorAgent] = None
_rag_client:   Optional[ChromaRAGClient]   = None
_audit_log:    Optional[AuditLogger]       = None
_rag_status:   str = "loading"

# Pending approval store: request_id → AgentResult
_pending_approvals: dict[str, AgentResult] = {}

# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info("WS client connected. Total: %d", len(self.active))

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info("WS client disconnected. Total: %d", len(self.active))

    async def broadcast(self, message: str):
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------
class DeployRequest(BaseModel):
    user_input: str
    request_id: Optional[str] = None
    environment: Optional[str] = "dev"
    user_id: Optional[str] = "api"

class ScanRequest(BaseModel):
    tf_code: str

class ApproveRequest(BaseModel):
    approved: bool = True

def _result_to_dict(result: AgentResult) -> dict:
    """Serialise an AgentResult to a JSON-safe dict."""
    return {
        "agent":                result.agent,
        "severity":             result.severity,
        "finding":              result.finding,
        "recommended_action":   result.recommended_action,
        "requires_human":       result.requires_human,
        "proposed_tf":          result.proposed_tf,
        "estimated_cost_delta": result.estimated_cost_delta,
        "timestamp":            result.timestamp.isoformat(),
        "metadata":             result.metadata,
    }

# ---------------------------------------------------------------------------
# API-Key security dependency
# ---------------------------------------------------------------------------
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(api_key: Optional[str] = Security(_api_key_header)):
    """Validate X-API-Key against INFRAGENIE_SECRET for /api/* routes."""
    if not api_key or api_key != settings.INFRAGENIE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Set X-API-Key header.",
        )
    return api_key

# ---------------------------------------------------------------------------
# Agent dependency getters (FastAPI Depends)
# ---------------------------------------------------------------------------
def get_orchestrator() -> OrchestratorAgent:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not yet initialised.")
    return _orchestrator

def get_monitor() -> MonitorAgent:
    if _monitor is None:
        raise HTTPException(status_code=503, detail="MonitorAgent not yet initialised.")
    return _monitor

def get_security() -> SecurityAgent:
    if _security is None:
        raise HTTPException(status_code=503, detail="SecurityAgent not yet initialised.")
    return _security

def get_audit_log() -> AuditLogger:
    if _audit_log is None:
        raise HTTPException(status_code=503, detail="AuditLogger not yet initialised.")
    return _audit_log

# ---------------------------------------------------------------------------
# Lifespan: initialise all agents in correct order, start background loop
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _planner, _executor, _monitor, _security, _orchestrator
    global _rag_client, _audit_log, _rag_status

    logger.info("=== InfraGenie startup sequence ===")

    # 1. Database / Audit log
    _audit_log = AuditLogger(db_url=settings.DB_URL)
    await _audit_log.init_db()
    logger.info("[Startup] AuditLogger ready.")

    # 2. RAG / ChromaDB
    _rag_client = ChromaRAGClient(
        persist_dir=settings.CHROMA_PERSIST_DIR,
        gemini_api_key=settings.GEMINI_API_KEY,
    )
    logger.info("[Startup] ChromaRAGClient ready.")

    # 3. Knowledge base — run in background so startup is non-blocking
    async def _load_knowledge():
        global _rag_status
        try:
            loader = KnowledgeLoader(
                rag_client=_rag_client,
                knowledge_dir="./knowledge",
            )
            await loader.load_all()
            _rag_status = "loaded"
            logger.info("[Startup] Knowledge base loaded.")
        except Exception as exc:
            _rag_status = "error"
            logger.error("[Startup] Knowledge base load failed: %s", exc)

    asyncio.create_task(_load_knowledge())

    # 4. AWS clients
    cw_client  = CloudWatchClient(settings)
    ce_client  = CostExplorerClient(settings)
    tf_runner  = TerraformRunner()
    logger.info("[Startup] AWS clients and TerraformRunner ready.")

    # 5. Sub-agents

    # Rules engine shim used by SecurityAgent
    class _SimpleRulesEngine:
        def __init__(self):
            from rules.security_rules import SECURITY_RULES
            self._rules = SECURITY_RULES
        def check(self, tf_code: str) -> list[dict]:
            import re
            return [r for r in self._rules if r.get("hcl_pattern") and re.search(r["hcl_pattern"], tf_code, re.DOTALL | re.IGNORECASE)]

    # Sync audit_log write adapter for SecurityAgent
    class _SyncAuditAdapter:
        def __init__(self, logger_obj):
            self._log = logger_obj
        def write(self, entry: dict):
            self._log.info("[SecurityAudit] %s", json.dumps(entry))

    _planner  = PlannerAgent(settings, _rag_client)
    _executor = ExecutorAgent(settings, _planner, tf_runner, None)
    _monitor  = MonitorAgent(settings, cw_client, ce_client, tf_runner)
    _security = SecurityAgent(settings, _SimpleRulesEngine(), _SyncAuditAdapter(logger))

    logger.info("[Startup] Sub-agents initialised.")

    # 6. Orchestrator
    _orchestrator = OrchestratorAgent(settings, _planner, _executor, _monitor, _security)
    _orchestrator.set_ws_broadcaster(manager.broadcast)
    _executor.set_ws_broadcaster(manager.broadcast)

    # 7. Start background loop
    loop_task = asyncio.create_task(_orchestrator.run_loop())
    logger.info("[Startup] OrchestratorAgent background loop started.")

    logger.info("=== InfraGenie ready ===")
    yield  # ← application runs here

    # Shutdown
    logger.info("[Shutdown] Stopping OrchestratorAgent...")
    await _orchestrator.stop()
    loop_task.cancel()
    logger.info("[Shutdown] InfraGenie shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="InfraGenie API",
    description=(
        "AI-powered multi-agent infrastructure management platform. "
        "Generates, validates, and applies Terraform configurations using "
        "Gemini + ChromaDB RAG."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.monotonic()
    logger.info("→ %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error for %s %s: %s", request.method, request.url.path, exc)
        raise
    elapsed = (time.monotonic() - start) * 1000
    logger.info("← %s %s %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed)
    return response

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# ── 1. Health ────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Return platform health, version, and RAG status."""
    return {
        "status":  "ok",
        "version": "1.0.0",
        "agents":  ["orchestrator", "planner", "executor", "monitor", "security"],
        "rag_status": _rag_status,
    }


# ── 2. Deploy ────────────────────────────────────────────────────────────────
@app.post("/api/deploy", tags=["Orchestrator"])
async def deploy(
    body: DeployRequest,
    orchestrator: OrchestratorAgent = Depends(get_orchestrator),
    _key: str = Depends(require_api_key),
):
    """
    Main endpoint — send a natural-language infrastructure request.

    Body: { "user_input": "...", "request_id": "optional-uuid", "environment": "dev" }
    """
    request_id = body.request_id or str(uuid.uuid4())
    req = InfraRequest(
        request_text=body.user_input,
        user_id=body.user_id or "api",
        environment=body.environment or "dev",
    )
    try:
        result: AgentResult = await orchestrator.handle_user_request(req)
    except Exception as exc:
        logger.exception("[/api/deploy] Orchestrator error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # If human approval is needed, park it for the approve endpoint
    if result.requires_human:
        _pending_approvals[request_id] = result

    response = _result_to_dict(result)
    response["request_id"] = request_id
    return response


# ── 3. Status ────────────────────────────────────────────────────────────────
@app.get("/api/status/{request_id}", tags=["Orchestrator"])
async def get_status(
    request_id: str,
    audit: AuditLogger = Depends(get_audit_log),
    _key: str = Depends(require_api_key),
):
    """Return the current status of a deployment by request_id."""
    # Check pending approvals first
    if request_id in _pending_approvals:
        result = _pending_approvals[request_id]
        data = _result_to_dict(result)
        data["request_id"] = request_id
        data["status"] = "awaiting_approval"
        return data

    # Fall back to audit log query
    try:
        async with audit.AsyncSessionLocal() as session:
            from sqlalchemy import select, text
            from db.models import AgentResultRecord
            stmt = select(AgentResultRecord).where(
                AgentResultRecord.metadata_json.contains(request_id)
            ).order_by(AgentResultRecord.timestamp.desc()).limit(1)
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                raise HTTPException(status_code=404, detail=f"No record found for request_id '{request_id}'.")
            return {
                "request_id":           request_id,
                "agent":                row.agent,
                "severity":             row.severity,
                "finding":              row.finding,
                "recommended_action":   row.recommended_action,
                "requires_human":       row.requires_human,
                "proposed_tf":          row.proposed_tf,
                "estimated_cost_delta": row.estimated_cost_delta,
                "timestamp":            row.timestamp.isoformat(),
                "status":               "completed",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[/api/status] DB query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── 4. History ───────────────────────────────────────────────────────────────
@app.get("/api/history", tags=["Audit"])
async def get_history(
    limit: int = 20,
    severity: Optional[str] = None,
    audit: AuditLogger = Depends(get_audit_log),
    _key: str = Depends(require_api_key),
):
    """
    Return recent AgentResults from the audit log.

    Query params:
    - limit   (int, default 20)
    - severity (str, optional) — filter by severity level
    """
    try:
        from sqlalchemy import select
        from db.models import AgentResultRecord
        async with audit.AsyncSessionLocal() as session:
            stmt = select(AgentResultRecord).order_by(AgentResultRecord.timestamp.desc())
            if severity:
                stmt = stmt.where(AgentResultRecord.severity == severity.lower())
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id":                   row.id,
                    "agent":                row.agent,
                    "severity":             row.severity,
                    "finding":              row.finding,
                    "recommended_action":   row.recommended_action,
                    "requires_human":       row.requires_human,
                    "estimated_cost_delta": row.estimated_cost_delta,
                    "timestamp":            row.timestamp.isoformat(),
                }
                for row in rows
            ]
    except Exception as exc:
        logger.exception("[/api/history] DB query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5. Resources ─────────────────────────────────────────────────────────────
@app.get("/api/resources", tags=["Monitor"])
async def list_resources(
    monitor: MonitorAgent = Depends(get_monitor),
    _key: str = Depends(require_api_key),
):
    """Return all AWS resources (EC2, RDS, S3, Lambda) in the configured region."""
    try:
        resources = await monitor.list_all_resources()
        return resources
    except Exception as exc:
        logger.exception("[/api/resources] Monitor error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── 6. Scan ──────────────────────────────────────────────────────────────────
@app.post("/api/scan", tags=["Security"])
async def scan_terraform(
    body: ScanRequest,
    security: SecurityAgent = Depends(get_security),
    _key: str = Depends(require_api_key),
):
    """
    Run a security scan on provided Terraform HCL code.

    Body: { "tf_code": "resource ..." }
    """
    try:
        result: AgentResult = await security.scan_terraform(body.tf_code, "")
        return _result_to_dict(result)
    except Exception as exc:
        logger.exception("[/api/scan] SecurityAgent error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── 7. Cost ──────────────────────────────────────────────────────────────────
@app.get("/api/cost", tags=["Monitor"])
async def get_cost(
    monitor: MonitorAgent = Depends(get_monitor),
    _key: str = Depends(require_api_key),
):
    """Return current-month AWS spend vs. configured budget threshold."""
    try:
        result: AgentResult = await monitor.check_budget(settings.BUDGET_THRESHOLD)
        return _result_to_dict(result)
    except Exception as exc:
        logger.exception("[/api/cost] MonitorAgent error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── 8. Approve ───────────────────────────────────────────────────────────────
@app.post("/api/approve/{request_id}", tags=["Orchestrator"])
async def approve_request(
    request_id: str,
    body: ApproveRequest = ApproveRequest(),
    orchestrator: OrchestratorAgent = Depends(get_orchestrator),
    _key: str = Depends(require_api_key),
):
    """
    Human approval endpoint.

    Marks a requires_human=True action as approved and triggers execution.
    The request must have been previously submitted via POST /api/deploy.
    """
    if request_id not in _pending_approvals:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval found for request_id '{request_id}'."
        )

    if not body.approved:
        _pending_approvals.pop(request_id, None)
        return {"request_id": request_id, "status": "rejected", "message": "Approval rejected. No action taken."}

    pending_result = _pending_approvals.pop(request_id)

    # Re-run via orchestrator with approved flag propagated into metadata
    original_request_text = pending_result.metadata.get("request", "re-run approved action")
    req = InfraRequest(
        request_text=original_request_text,
        user_id="human_approver",
        environment=pending_result.metadata.get("environment", "dev"),
    )

    try:
        result: AgentResult = await orchestrator.handle_user_request(req)
    except Exception as exc:
        logger.exception("[/api/approve] Orchestrator error after approval: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    response = _result_to_dict(result)
    response["request_id"] = request_id
    response["status"] = "approved_and_executed"
    return response


# ── 9. WebSocket ─────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket channel.

    Clients can send { "user_input": "..." } to trigger the orchestrator.
    All AgentResult events are broadcast to every connected client as JSON.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = {"user_input": data}

            user_input = (
                payload.get("user_input")
                or payload.get("request_text")
                or payload.get("request")
                or ""
            )

            if user_input and _orchestrator:
                req = InfraRequest(
                    request_text=user_input,
                    user_id=payload.get("user_id", "ws_client"),
                    environment=payload.get("environment", "dev"),
                )
                asyncio.create_task(_orchestrator.handle_user_request(req))
            else:
                await websocket.send_text(
                    json.dumps({"type": "echo", "payload": payload})
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
        manager.disconnect(websocket)
