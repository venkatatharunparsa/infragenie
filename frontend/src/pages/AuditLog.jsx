import React, { useCallback, useEffect, useState } from "react";
import { getHistory } from "../api/client";

const SEVERITIES = ["", "critical", "high", "medium", "low", "info"];

const SEV_BADGE = {
  critical: "bg-red-900 text-red-300",
  high:     "bg-orange-900 text-orange-300",
  medium:   "bg-yellow-900 text-yellow-300",
  low:      "bg-blue-900 text-blue-300",
  info:     "bg-gray-800 text-gray-400",
};

export default function AuditLog() {
  const [rows,      setRows]      = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const [severity,  setSeverity]  = useState("");
  const [limit,     setLimit]     = useState(50);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await getHistory(limit, severity || null);
      setRows(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [limit, severity]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Audit Log</h1>
          <p className="text-xs text-gray-500 mt-0.5">All agent actions and decisions</p>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <select
            id="severity-filter"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="input-field text-sm w-36"
          >
            <option value="">All severities</option>
            {SEVERITIES.filter(Boolean).map((s) => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>

          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="input-field text-sm w-24"
          >
            {[20, 50, 100, 200].map((n) => (
              <option key={n} value={n}>{n} rows</option>
            ))}
          </select>

          <button
            onClick={load}
            disabled={loading}
            className="btn-ghost text-sm"
          >
            {loading ? "Loading…" : "↻ Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">{error}</p>
      )}

      {/* Table */}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-widest">
              <th className="px-4 py-3 text-left">Timestamp</th>
              <th className="px-4 py-3 text-left">Agent</th>
              <th className="px-4 py-3 text-left">Severity</th>
              <th className="px-4 py-3 text-left">Finding</th>
              <th className="px-4 py-3 text-left">Action</th>
              <th className="px-4 py-3 text-left">Human</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-xs text-gray-600 animate-pulse">
                  Loading audit log…
                </td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-xs text-gray-700 italic">
                  No audit log entries found.
                </td>
              </tr>
            )}
            {!loading && rows.map((row, i) => (
              <tr
                key={row.id || i}
                className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50 transition-colors"
              >
                <td className="px-4 py-2.5 text-xs text-gray-500 tabular-nums whitespace-nowrap">
                  {row.timestamp ? new Date(row.timestamp).toLocaleString() : "—"}
                </td>
                <td className="px-4 py-2.5">
                  <span className="text-blue-400 font-mono text-xs">{row.agent}</span>
                </td>
                <td className="px-4 py-2.5">
                  <span className={`badge ${SEV_BADGE[(row.severity || "info").toLowerCase()] || SEV_BADGE.info}`}>
                    {(row.severity || "info").toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-xs text-gray-300 max-w-sm">
                  <span className="line-clamp-2">{row.finding}</span>
                </td>
                <td className="px-4 py-2.5 text-xs text-gray-500 max-w-xs">
                  <span className="line-clamp-1">{row.recommended_action}</span>
                </td>
                <td className="px-4 py-2.5 text-center">
                  {row.requires_human ? (
                    <span className="text-yellow-500 text-xs">⚠️</span>
                  ) : (
                    <span className="text-gray-700 text-xs">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Row count */}
      {!loading && rows.length > 0 && (
        <p className="text-xs text-gray-700 text-right">
          Showing {rows.length} of {limit} requested rows
        </p>
      )}
    </div>
  );
}
