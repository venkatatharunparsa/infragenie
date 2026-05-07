"""
OrchestratorAgent
-----------------
Master agent that runs a continuous perceive-reason-plan-act-observe loop
and delegates to specialist sub-agents (Planner, Executor, Monitor, Security).
Implements a 4-tier intelligence router to decide how each situation is handled.
"""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime
from typing import Optional
from backend.utils.genai_client import GenAIClientPool

from google import genai

from .models import AgentResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight rule engines (wrap the static rule lists)
# ─────────────────────────────────────────────────────────────────────────────

class SecurityRulesEngine:
    """Evaluates HCL / resource dicts against the static SECURITY_RULES set."""

    def __init__(self):
        from rules.security_rules import SECURITY_RULES
        self._rules = SECURITY_RULES

    def check(self, hcl: str) -> list[dict]:
        """Return list of violated security rules for *hcl*."""
        import re
        violations = []
        for rule in self._rules:
            if rule.get("id") == "SEC-002" and "aws_s3_bucket_public_access_block" in hcl:
                continue  # Separate resource block pattern — compliant
            pattern = rule.get("hcl_pattern", "")
            if pattern and re.search(pattern, hcl, re.DOTALL | re.IGNORECASE):
                violations.append(rule)
        return violations

    def has_blockers(self, hcl: str = "") -> bool:
        """Return True if any critical/high rule is violated."""
        return any(
            r["severity"] in ("critical", "high")
            for r in self.check(hcl)
        )


class PolicyRulesEngine:
    """Evaluates plans against POLICY_RULES."""

    def __init__(self):
        from rules.policy_rules import POLICY_RULES
        self._rules = POLICY_RULES

    def requires_human(self, context: dict) -> Optional[str]:
        """Return the first policy rule ID that requires human approval, or None."""
        for rule in self._rules:
            if rule.get("action") == "require_human":
                # Production environment check
                if "production" in str(context).lower():
                    return rule["id"]
            if rule.get("action") == "block":
                if rule.get("id") == "POL-001":
                    threshold = float(context.get("budget_threshold", 1e9))
                    delta_str = context.get("estimated_cost_delta", "$0")
                    try:
                        delta = float(delta_str.replace("$", "").replace("+", "").replace("/mo", ""))
                        if delta > threshold:
                            return rule["id"]
                    except ValueError:
                        pass
        return None


# ─────────────────────────────────────────────────────────────────────────────
# InfraRequest shim (used until db.models is wired up)
# ─────────────────────────────────────────────────────────────────────────────

class InfraRequest:
    """Minimal request object passed into the orchestrator from the API layer."""

    def __init__(self, request_text: str, user_id: str = "system", environment: str = "dev"):
        self.request_text = request_text
        self.user_id = user_id
        self.environment = environment
        self.created_at = datetime.utcnow()


# ─────────────────────────────────────────────────────────────────────────────
# OrchestratorAgent
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    Master orchestrator that continuously monitors infrastructure and handles
    user-triggered requests via a perceive → reason → plan-act → observe cycle.

    Architecture
    ────────────
    • run_loop()          — background 1 hour heartbeat
    • handle_user_request()— foreground request handler (interrupts loop)
    • _perceive()         — snapshot current AWS state via MonitorAgent
    • _reason()           — Gemini-powered situation analysis
    • _plan_and_act()     — route to correct sub-agent with security gates
    • _observe()          — store result in memory, emit via WebSocket
    • _route_decision()   — 4-tier intelligence tier selector
    """

    LOOP_INTERVAL_SECONDS = 3600  # 1 hour — saves your quota for real requests
    MEMORY_MAX_SIZE       = 100
    REASON_CONTEXT_SIZE   = 5      # last N results sent to Gemini

    def __init__(self, config, planner, executor, monitor, security_agent):
        """
        Parameters
        ----------
        config         : Settings  — application configuration
        planner        : PlannerAgent
        executor       : ExecutorAgent
        monitor        : MonitorAgent
        security_agent : SecurityAgent
        """
        self.config         = config
        self.planner        = planner
        self.executor       = executor
        self.monitor        = monitor
        self.security_agent = security_agent

        # Sub-systems
        self.security_rules = SecurityRulesEngine()
        self.policy_rules   = PolicyRulesEngine()

        # State
        self.current_infra_state: dict = {}
        self._memory: deque[AgentResult] = deque(maxlen=self.MEMORY_MAX_SIZE)

        # Loop control
        self._loop_running:  bool = False
        self._interrupt:     asyncio.Event = asyncio.Event()
        self._ws_broadcast   = None   # injected by the API layer (callable)

        # Gemini with fallback support
        self.client_pool = GenAIClientPool(
            primary_key=config.GEMINI_API_KEY,
            fallback_key=config.GEMINI_FALLBACK_API_KEY
        )

        logger.info("[Orchestrator] Initialised with %d security rules.", len(self.security_rules._rules))

    # ── Public: loop ─────────────────────────────────────────────────────────

    async def run_loop(self):
        """
        Infinite background loop — runs every LOOP_INTERVAL_SECONDS.
        Performs a full perceive-reason-plan-act cycle on each tick.
        Can be interrupted early by handle_user_request() via self._interrupt.
        """
        self._loop_running = True
        logger.info("[Orchestrator] Background loop started (interval=%ds).", self.LOOP_INTERVAL_SECONDS)

        while self._loop_running:
            try:
                self._interrupt.clear()
                logger.debug("[Orchestrator] Loop tick — perceiving...")

                perception = await self._perceive()
                reasoning  = await self._reason(perception)
                result     = await self._plan_and_act(reasoning)
                await self._observe(result)

            except asyncio.CancelledError:
                logger.info("[Orchestrator] Loop cancelled.")
                break
            except Exception as exc:                          # never crash the loop
                logger.exception("[Orchestrator] Unhandled error in loop tick: %s", exc)

            # Wait for the interval OR an early interrupt
            try:
                await asyncio.wait_for(
                    self._interrupt.wait(),
                    timeout=self.LOOP_INTERVAL_SECONDS,
                )
                logger.debug("[Orchestrator] Loop interrupted early by user request.")
            except asyncio.TimeoutError:
                pass   # normal — interval elapsed

        self._loop_running = False
        logger.info("[Orchestrator] Background loop stopped.")

    # ── Public: user request entry point ─────────────────────────────────────

    async def handle_user_request(self, request: InfraRequest) -> AgentResult:
        """
        Handle a user-triggered infrastructure request.

        Interrupts the background loop cycle immediately, runs the full
        perceive-reason-plan-act-observe pipeline for this request, and
        returns the final AgentResult to the caller (API layer).

        Parameters
        ----------
        request : InfraRequest
            The user's infrastructure request.

        Returns
        -------
        AgentResult
            Consolidated result from the relevant sub-agent.
        """
        logger.info("[Orchestrator] User request received: '%s'", request.request_text[:80])
        self._interrupt.set()   # wake loop early

        try:
            # Deploy requests always go to Planner first — never to Monitor.
            user_input = getattr(request, "request_text", "")
            user_input_lower = user_input.lower()
            request_id = getattr(request, "request_id", "default")

            deploy_keywords = ["create", "build", "deploy", "provision", "make", "setup", "add"]
            destroy_keywords = ["destroy", "delete", "remove", "terminate"]

            if any(k in user_input_lower for k in destroy_keywords):
                result = AgentResult(
                    agent="orchestrator",
                    severity="high",
                    finding="Destructive action requested — human approval required",
                    recommended_action="destroy",
                    requires_human=True,
                    timestamp=datetime.utcnow(),
                    metadata={"request": user_input, "request_id": request_id},
                )
                await self._observe(result)
                return result

            if any(k in user_input_lower for k in deploy_keywords):
                planner_result: AgentResult = await self.planner.run({
                    "request": user_input,
                    "user_request": user_input,
                    "request_id": request_id,
                })

                if planner_result.proposed_tf:
                    security_result: AgentResult = await self.security_agent.run({
                        "action": "scan_tf",
                        "terraform_hcl": planner_result.proposed_tf,
                        "workspace_path": planner_result.workspace_path,
                    })
                    if security_result.severity.lower() in ("critical", "high"):
                        security_result.workspace_path = planner_result.workspace_path
                        security_result.metadata["request"] = user_input
                        security_result.metadata["request_id"] = request_id
                        await self._observe(security_result)
                        return security_result

                planner_result.requires_human = True
                planner_result.metadata["request"] = user_input
                planner_result.metadata["request_id"] = request_id
                await self._observe(planner_result)
                return planner_result

            perception = await self._perceive()
            reasoning  = await self._reason(perception, request)
            result     = await self._plan_and_act(reasoning, request)
            await self._observe(result)
            return result
        except Exception as exc:
            logger.exception("[Orchestrator] Error handling user request: %s", exc)
            return AgentResult(
                agent="orchestrator",
                severity="high",
                finding=f"Orchestrator error: {exc}",
                recommended_action="Check backend logs for details.",
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"error": str(exc), "request": request.request_text},
            )

    # ── Step 1: Perceive ─────────────────────────────────────────────────────

    async def _perceive(self) -> dict:
        """
        Snapshot current AWS infrastructure state via the MonitorAgent.

        Returns
        -------
        dict
            Keys: infra_state, alerts, metrics, timestamp
        """
        logger.debug("[Orchestrator] _perceive() called.")
        try:
            monitor_result: AgentResult = await self.monitor.run({"action": "snapshot"})
            self.current_infra_state = monitor_result.metadata.get("infra_state", {})

            perception = {
                "infra_state": self.current_infra_state,
                "alerts":      monitor_result.metadata.get("alerts", []),
                "metrics":     monitor_result.metadata.get("metrics", {}),
                "timestamp":   datetime.utcnow().isoformat(),
                "severity":    monitor_result.severity,
                "finding":     monitor_result.finding,
            }
        except Exception as exc:
            logger.warning("[Orchestrator] Perception failed (%s) — using empty state.", exc)
            perception = {
                "infra_state": {},
                "alerts":      [],
                "metrics":     {},
                "timestamp":   datetime.utcnow().isoformat(),
                "severity":    "info",
                "finding":     "Monitor unavailable.",
            }

        logger.debug("[Orchestrator] Perception complete: %d alerts.", len(perception["alerts"]))
        return perception

    # ── Step 2: Reason ───────────────────────────────────────────────────────

    async def _reason(self, perception: dict, request: Optional[InfraRequest] = None) -> dict:
        """
        Use Gemini to analyse the current situation and decide what to do.

        Parameters
        ----------
        perception : dict
            Output of _perceive().
        request : InfraRequest, optional
            Active user request (None during autonomous loop ticks).

        Returns
        -------
        dict
            Keys: situation_summary, recommended_action, which_agent, urgency
        """
        # Tier 1 — if no user request and no alerts, skip Gemini entirely.
        if request is None and not perception.get("alerts"):
            return {
                "situation_summary": "Routine snapshot — no anomalies",
                "recommended_action": "monitor",
                "which_agent": "monitor",
                "urgency": "low",
            }

        logger.debug("[Orchestrator] _reason() called.")

        # Build context from memory
        recent = list(self._memory)[-self.REASON_CONTEXT_SIZE:]
        memory_ctx = [
            {
                "agent":             r.agent,
                "severity":          r.severity,
                "finding":           r.finding,
                "recommended_action": r.recommended_action,
                "timestamp":         r.timestamp.isoformat(),
            }
            for r in recent
        ]

        prompt_parts = [
            "You are the reasoning core of InfraGenie, an AI infrastructure management platform.",
            "",
            "## Current Infrastructure State",
            json.dumps(perception, indent=2),
            "",
            "## Recent Agent Memory (last 5 results)",
            json.dumps(memory_ctx, indent=2),
        ]

        if request:
            prompt_parts += [
                "",
                "## Active User Request",
                f"User: {request.user_id}",
                f"Environment: {request.environment}",
                f"Request: {request.request_text}",
            ]

        prompt_parts += [
            "",
            "Based on the above, respond with ONLY a valid JSON object with these keys:",
            '  "situation_summary": string — 1-2 sentence summary of current state',
            '  "recommended_action": string — what should be done next',
            '  "which_agent": one of ["planner","executor","monitor","security","none"]',
            '  "urgency": one of ["low","medium","high","critical"]',
        ]

        prompt = "\n".join(prompt_parts)

        try:
            response = await asyncio.to_thread(
                self.client_pool.generate_content,
                model='gemini-flash-latest',
                contents=prompt
            )
            raw = self.client_pool.extract_text(response)
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            reasoning = json.loads(raw)
            logger.info("[Orchestrator] Reasoning: urgency=%s, agent=%s",
                        reasoning.get("urgency"), reasoning.get("which_agent"))
        except Exception as exc:
            logger.warning("[Orchestrator] Gemini reasoning failed (%s) — using fallback.", exc)
            reasoning = {
                "situation_summary":  "Reasoning unavailable due to API error.",
                "recommended_action": "Run a manual health check.",
                "which_agent":        "monitor",
                "urgency":            "low",
            }

        return reasoning

    # ── Step 3: Plan and Act ─────────────────────────────────────────────────

    async def _plan_and_act(self, reasoning: dict, request: Optional[InfraRequest] = None) -> AgentResult:
        """
        Route to the appropriate sub-agent based on Gemini's reasoning.

        Security gate runs BEFORE every executor call:
          1. SecurityAgent check → block if critical/high violations found.
          2. PolicyRulesEngine  → set requires_human=True if policy demands it.

        Parameters
        ----------
        reasoning : dict
            Output of _reason().
        request : InfraRequest, optional
            Active user request.

        Returns
        -------
        AgentResult
        """
        which_agent = reasoning.get("which_agent", "monitor")
        urgency     = reasoning.get("urgency", "low")
        req_text    = request.request_text if request else ""
        environment = request.environment  if request else "dev"

        logger.info("[Orchestrator] _plan_and_act() → routing to '%s' (urgency=%s).", which_agent, urgency)

        # ── Tier selection ───────────────────────────────────────────────────
        tier = await self._route_decision({
            "which_agent":       which_agent,
            "urgency":           urgency,
            "request":           req_text,
            "environment":       environment,
            "budget_threshold":  self.config.BUDGET_THRESHOLD,
        })
        logger.info("[Orchestrator] Intelligence tier: %d", tier)

        # ── Tier 1: Security blocker ─────────────────────────────────────────
        if tier == 1:
            return AgentResult(
                agent="orchestrator",
                severity="critical",
                finding="Action blocked by security rules engine before routing.",
                recommended_action="Resolve security violations and resubmit.",
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"tier": 1, "reasoning": reasoning},
            )

        # ── Tier 4: Human approval required ──────────────────────────────────
        if tier == 4:
            logger.info("[Orchestrator] Tier 4 — requires human approval.")
            return AgentResult(
                agent="orchestrator",
                severity="medium",
                finding=reasoning.get("situation_summary", "Human approval required."),
                recommended_action=reasoning.get("recommended_action", "Approve via the InfraGenie UI."),
                requires_human=True,
                timestamp=datetime.utcnow(),
                metadata={"tier": 4, "reasoning": reasoning},
            )

        # ── Route to sub-agents ──────────────────────────────────────────────
        # Prefer the request_id attached by the API layer on the InfraRequest object
        # (set as req.request_id in the deploy endpoint) so the workspace folder name
        # matches what the approve endpoint expects.
        request_id_ctx = getattr(request, "request_id", None) or reasoning.get("request_id", "unknown")
        agent_input = {
            "intent":        req_text,
            "request":       req_text,
            "environment":   environment,
            "reasoning":     reasoning,
            "urgency":       urgency,
            "request_id":    request_id_ctx,
            "workspace_dir": getattr(self.config, "TERRAFORM_WORKSPACE_DIR", "./terraform_workspace"),
        }

        if which_agent == "planner":
            result: AgentResult = await self.planner.run(agent_input)

        elif which_agent == "executor":
            # ── Security gate (always runs before executor) ──────────────────
            proposed_hcl = agent_input.get("terraform_hcl", "")
            sec_result: AgentResult = await self.security_agent.run({
                "terraform_hcl": proposed_hcl,
                "resource_ids":  [],
            })
            if sec_result.severity in ("critical", "high"):
                logger.warning("[Orchestrator] Security gate blocked execution.")
                return AgentResult(
                    agent="orchestrator",
                    severity=sec_result.severity,
                    finding=f"Execution blocked by SecurityAgent: {sec_result.finding}",
                    recommended_action=sec_result.recommended_action,
                    requires_human=True,
                    proposed_tf=proposed_hcl,
                    timestamp=datetime.utcnow(),
                    metadata={"security_result": sec_result.metadata, "tier": tier},
                )

            # ── Policy gate ──────────────────────────────────────────────────
            policy_ctx = {
                "environment":          environment,
                "estimated_cost_delta": agent_input.get("estimated_cost_delta", "$0"),
                "budget_threshold":     self.config.BUDGET_THRESHOLD,
            }
            policy_block_id = self.policy_rules.requires_human(policy_ctx)
            if policy_block_id:
                logger.info("[Orchestrator] Policy %s requires human approval.", policy_block_id)
                return AgentResult(
                    agent="orchestrator",
                    severity="medium",
                    finding=f"Policy {policy_block_id} requires human approval before execution.",
                    recommended_action="Approve via the InfraGenie console.",
                    requires_human=True,
                    timestamp=datetime.utcnow(),
                    metadata={"policy_rule": policy_block_id, "tier": tier},
                )

            result = await self.executor.run({**agent_input, "approved": True})

        elif which_agent == "security":
            result = await self.security_agent.run(agent_input)

        elif which_agent == "monitor":
            result = await self.monitor.run(agent_input)

        else:
            # "none" or unknown — return reasoning summary as info result
            result = AgentResult(
                agent="orchestrator",
                severity="info",
                finding=reasoning.get("situation_summary", "No action required."),
                recommended_action=reasoning.get("recommended_action", "Continue monitoring."),
                requires_human=False,
                timestamp=datetime.utcnow(),
                metadata={"tier": tier, "reasoning": reasoning},
            )

        return result

    # ── Step 4: Observe ──────────────────────────────────────────────────────

    async def _observe(self, result: AgentResult):
        """
        Store result in memory and emit it to all connected WebSocket clients.

        Parameters
        ----------
        result : AgentResult
            The result produced by _plan_and_act().
        """
        self._memory.append(result)
        logger.info("[Orchestrator] _observe(): agent=%s, severity=%s, requires_human=%s",
                    result.agent, result.severity, result.requires_human)

        if self._ws_broadcast is not None:
            payload = {
                "type": "agent_result",
                "payload": {
                    "agent":             result.agent,
                    "severity":          result.severity,
                    "finding":           result.finding,
                    "recommended_action": result.recommended_action,
                    "requires_human":    result.requires_human,
                    "proposed_tf":       result.proposed_tf,
                    "estimated_cost_delta": result.estimated_cost_delta,
                    "timestamp":         result.timestamp.isoformat(),
                    "metadata":          result.metadata,
                },
            }
            try:
                await self._ws_broadcast(json.dumps(payload))
                logger.debug("[Orchestrator] WebSocket broadcast sent.")
            except Exception as exc:
                logger.warning("[Orchestrator] WebSocket broadcast failed: %s", exc)

    # ── 4-Tier Intelligence Router ────────────────────────────────────────────

    async def _route_decision(self, context: dict) -> int:
        """
        Determine which intelligence tier applies to the current context.

        Tier 1 — Security blocker:   a security rule with critical/high severity
                                      is violated → block immediately, no LLM call.
        Tier 2 — Memory hit:          a sufficiently similar past action exists in
                                      memory → reuse / fast-path decision.
        Tier 3 — Complex reasoning:   novel situation requiring Gemini analysis
                                      (already done in _reason).
        Tier 4 — Human in the loop:   policy engine mandates human approval before
                                      any automated action proceeds.

        Parameters
        ----------
        context : dict
            Must include keys: which_agent, urgency, request, environment,
            budget_threshold.

        Returns
        -------
        int
            1, 2, 3, or 4.
        """
        hcl       = context.get("terraform_hcl", "")
        env       = context.get("environment", "dev")
        urgency   = context.get("urgency", "low")
        req_text  = context.get("request", "")

        # ── Tier 1: Security blockers ────────────────────────────────────────
        if hcl and self.security_rules.has_blockers(hcl):
            logger.info("[Router] Tier 1 — security blocker detected.")
            return 1

        # Urgency-based early block (critical with no HCL still warrants Tier 1)
        if urgency == "critical" and context.get("which_agent") == "executor" and not hcl:
            logger.info("[Router] Tier 1 — critical urgency executor call with no HCL.")
            return 1

        # ── Tier 4: Policy / human approval ─────────────────────────────────
        policy_id = self.policy_rules.requires_human(context)
        if policy_id:
            logger.info("[Router] Tier 4 — policy %s requires human.", policy_id)
            return 4

        # Production environment always requires human for executor
        if env == "production" and context.get("which_agent") == "executor":
            logger.info("[Router] Tier 4 — production executor gated.")
            return 4

        # ── Tier 2: Memory hit ────────────────────────────────────────────────
        if req_text:
            req_lower = req_text.lower()
            for past in list(self._memory)[-20:]:   # search last 20 results
                if (
                    past.severity not in ("critical", "high")
                    and not past.requires_human
                    and any(word in past.finding.lower() for word in req_lower.split()[:5])
                ):
                    logger.info("[Router] Tier 2 — similar past action found in memory.")
                    return 2

        # ── Tier 3: Needs full reasoning (default) ────────────────────────────
        logger.info("[Router] Tier 3 — complex reasoning path.")
        return 3

    # ── Utility: inject WebSocket broadcaster ────────────────────────────────

    def set_ws_broadcaster(self, broadcast_fn):
        """
        Inject the WebSocket broadcast callable from the FastAPI layer.

        Parameters
        ----------
        broadcast_fn : coroutine function
            Async callable that accepts a JSON string and broadcasts it to all
            connected WebSocket clients (e.g. ConnectionManager.broadcast).
        """
        self._ws_broadcast = broadcast_fn
        logger.info("[Orchestrator] WebSocket broadcaster registered.")

    # ── Utility: graceful shutdown ────────────────────────────────────────────

    async def stop(self):
        """Signal the background loop to stop after the current tick."""
        self._loop_running = False
        self._interrupt.set()
        logger.info("[Orchestrator] Stop signal sent.")
