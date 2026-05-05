import React, { useState } from "react";
import { approveAction } from "../api/client";

export default function ApprovalModal({ result, requestId, onClose, onDone }) {
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  if (!result) return null;

  async function handleApprove() {
    setLoading(true); setError(null);
    try {
      const res = await approveAction(requestId, true);
      onDone?.(res);
      onClose?.();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleReject() {
    approveAction(requestId, false).catch(() => {});
    onClose?.();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-yellow-700 rounded-2xl shadow-2xl max-w-2xl w-full flex flex-col gap-4 p-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-yellow-400 flex items-center gap-2">
            <span>⚠️</span> Human Approval Required
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">×</button>
        </div>

        {/* What is being requested */}
        <div className="bg-gray-800 rounded-xl p-4 space-y-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest">Requested Action</p>
          <p className="text-sm text-gray-200 leading-relaxed">{result.finding}</p>
          {result.recommended_action && (
            <p className="text-xs text-blue-400">→ {result.recommended_action}</p>
          )}
        </div>

        {/* Cost delta */}
        {result.estimated_cost_delta && result.estimated_cost_delta !== "$0.00" && (
          <div className="flex items-center gap-2 bg-emerald-950 border border-emerald-800 rounded-xl px-4 py-3">
            <span className="text-emerald-400 font-semibold">💰 Estimated cost impact:</span>
            <span className="text-emerald-300">{result.estimated_cost_delta}</span>
          </div>
        )}

        {/* Proposed Terraform */}
        {result.proposed_tf && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Proposed Terraform</p>
            <pre className="text-xs bg-gray-950 border border-gray-800 rounded-xl p-4 overflow-x-auto text-green-400 max-h-64">
              {result.proposed_tf}
            </pre>
          </div>
        )}

        {error && (
          <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">{error}</p>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button onClick={handleApprove} disabled={loading} className="btn-primary flex-1 justify-center">
            {loading ? "Executing…" : "✅ Approve & Execute"}
          </button>
          <button onClick={handleReject} disabled={loading} className="btn-danger flex-1 justify-center">
            ❌ Reject
          </button>
        </div>
      </div>
    </div>
  );
}
