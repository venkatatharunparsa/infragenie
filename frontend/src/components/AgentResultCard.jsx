import React from "react";

// ── Badge helpers ──────────────────────────────────────────────────────────

const SEVERITY_STYLES = {
  critical: "bg-red-900 text-red-300 ring-1 ring-red-700",
  high:     "bg-orange-900 text-orange-300 ring-1 ring-orange-700",
  medium:   "bg-yellow-900 text-yellow-300 ring-1 ring-yellow-700",
  low:      "bg-blue-900 text-blue-300 ring-1 ring-blue-700",
  info:     "bg-gray-800 text-gray-400 ring-1 ring-gray-700",
};

const SEVERITY_DOT = {
  critical: "bg-red-500",
  high:     "bg-orange-500",
  medium:   "bg-yellow-500",
  low:      "bg-blue-500",
  info:     "bg-gray-500",
};

const AGENT_STYLES = {
  orchestrator: "bg-violet-900 text-violet-300",
  planner:      "bg-blue-900 text-blue-300",
  executor:     "bg-cyan-900 text-cyan-300",
  monitor:      "bg-emerald-900 text-emerald-300",
  security:     "bg-rose-900 text-rose-300",
};

function SeverityBadge({ severity }) {
  const sev = (severity || "info").toLowerCase();
  return (
    <span className={`badge ${SEVERITY_STYLES[sev] || SEVERITY_STYLES.info}`}>
      <span className={`w-1.5 h-1.5 rounded-full mr-1 ${SEVERITY_DOT[sev] || "bg-gray-500"}`} />
      {sev.toUpperCase()}
    </span>
  );
}

function AgentBadge({ agent }) {
  const style = AGENT_STYLES[agent?.toLowerCase()] || "bg-gray-800 text-gray-400";
  return <span className={`badge ${style}`}>{agent || "unknown"}</span>;
}

// ── Main component ─────────────────────────────────────────────────────────

export default function AgentResultCard({ result, requestId, onApprove }) {
  if (!result) return null;

  const {
    agent,
    severity,
    finding,
    recommended_action,
    requires_human,
    proposed_tf,
    estimated_cost_delta,
    timestamp,
  } = result;

  const ts = timestamp
    ? new Date(timestamp).toLocaleString()
    : "—";

  return (
    <div className="card flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <AgentBadge agent={agent} />
          <SeverityBadge severity={severity} />
        </div>
        <span className="text-xs text-gray-600">{ts}</span>
      </div>

      {/* Human approval banner */}
      {requires_human && (
        <div className="flex items-center justify-between gap-3 bg-yellow-950 border border-yellow-800 rounded-lg px-3 py-2">
          <span className="text-yellow-400 text-xs font-semibold flex items-center gap-1.5">
            <span>⚠️</span> Human approval required
          </span>
          {onApprove && requestId && (
            <button
              onClick={() => onApprove(requestId, result)}
              className="text-xs bg-yellow-700 hover:bg-yellow-600 text-white font-semibold px-3 py-1 rounded-lg transition-colors"
            >
              Review &amp; Approve
            </button>
          )}
        </div>
      )}

      {/* Finding */}
      <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{finding}</p>

      {/* Recommended action */}
      {recommended_action && (
        <div className="flex items-start gap-2">
          <span className="text-blue-500 mt-0.5">→</span>
          <p className="text-xs text-gray-400">{recommended_action}</p>
        </div>
      )}

      {/* Cost delta */}
      {estimated_cost_delta && estimated_cost_delta !== "$0.00" && (
        <div className="flex items-center gap-1.5 text-xs text-emerald-400">
          <span>💰</span>
          <span>{estimated_cost_delta}</span>
        </div>
      )}

      {/* Proposed TF code */}
      {proposed_tf && (
        <details className="group">
          <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 transition-colors select-none">
            View Terraform plan ▸
          </summary>
          <pre className="mt-2 text-xs bg-gray-950 border border-gray-800 rounded-lg p-3 overflow-x-auto text-green-400 max-h-64">
            {proposed_tf}
          </pre>
        </details>
      )}
    </div>
  );
}
