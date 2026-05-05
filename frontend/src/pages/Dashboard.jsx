import React, { useState } from "react";
import LiveLogFeed from "../components/LiveLogFeed";
import CostWidget from "../components/CostWidget";
import InfraMap from "../components/InfraMap";
import ChatInput from "../components/ChatInput";
import AgentResultCard from "../components/AgentResultCard";
import ApprovalModal from "../components/ApprovalModal";

export default function Dashboard() {
  const [results,  setResults]  = useState([]);
  const [approval, setApproval] = useState(null); // {result, requestId}

  function handleResult(result) {
    setResults((prev) => [result, ...prev].slice(0, 20));
    if (result.requires_human) {
      setApproval({ result, requestId: result.request_id || `req-${Date.now()}` });
    }
  }

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 flex flex-col gap-6">
      {/* Page title */}
      <div>
        <h1 className="text-xl font-bold text-white">Dashboard</h1>
        <p className="text-xs text-gray-500 mt-0.5">Real-time infrastructure overview and deployment console</p>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Live feed */}
        <div className="lg:col-span-2 flex flex-col gap-4" style={{ minHeight: "520px" }}>
          <div className="flex-1">
            <LiveLogFeed onNewResult={handleResult} />
          </div>

          {/* Recent results from REST deploys */}
          {results.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest">Recent Responses</h3>
              {results.slice(0, 3).map((r, i) => (
                <AgentResultCard
                  key={i}
                  result={r}
                  requestId={r.request_id}
                  onApprove={(rid, res) => setApproval({ result: res, requestId: rid })}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right: Widgets */}
        <div className="flex flex-col gap-4">
          <CostWidget />
          <InfraMap />
        </div>
      </div>

      {/* Chat input at bottom */}
      <ChatInput onResult={handleResult} />

      {/* Approval modal */}
      {approval && (
        <ApprovalModal
          result={approval.result}
          requestId={approval.requestId}
          onClose={() => setApproval(null)}
          onDone={(res) => { handleResult(res); setApproval(null); }}
        />
      )}
    </div>
  );
}
