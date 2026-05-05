import React, { useEffect, useState } from "react";
import { getCost } from "../api/client";

function clamp(v, min, max) { return Math.min(Math.max(v, min), max); }

export default function CostWidget() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  async function load() {
    setLoading(true); setError(null);
    try { setData(await getCost()); }
    catch (err) { setError(err.response?.data?.detail || err.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const spend     = data?.metadata?.spend_usd  || 0;
  const threshold = data?.metadata?.threshold  || 500;
  const pct       = data?.metadata?.pct        || 0;
  const barColor  = pct >= 80 ? "bg-red-500" : pct >= 50 ? "bg-yellow-500" : "bg-green-500";
  const textColor = pct >= 80 ? "text-red-400" : pct >= 50 ? "text-yellow-400" : "text-green-400";

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300">AWS Cost — This Month</h2>
        <button onClick={load} disabled={loading} className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-40">
          {loading ? "…" : "↻"}
        </button>
      </div>
      {loading && <div className="text-xs text-gray-600 animate-pulse">Fetching…</div>}
      {error && <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">{error}</p>}
      {!loading && !error && data && (
        <>
          <div className="flex items-end justify-between">
            <div>
              <span className={`text-3xl font-bold tabular-nums ${textColor}`}>${spend.toFixed(2)}</span>
              <span className="text-xs text-gray-600 ml-2">/ ${threshold.toFixed(2)} budget</span>
            </div>
            <span className={`text-sm font-semibold ${textColor}`}>{pct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div className={`h-2 rounded-full transition-all duration-700 ${barColor}`} style={{ width: `${clamp(pct,0,100)}%` }} />
          </div>
          <p className="text-xs text-gray-500">{data.finding}</p>
          {data.estimated_cost_delta && <span className="text-xs text-gray-600">{data.estimated_cost_delta}</span>}
        </>
      )}
    </div>
  );
}
