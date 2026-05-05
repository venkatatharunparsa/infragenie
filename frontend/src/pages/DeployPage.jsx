import React, { useState } from "react";
import ChatInput from "../components/ChatInput";
import AgentResultCard from "../components/AgentResultCard";
import ApprovalModal from "../components/ApprovalModal";

export default function DeployPage() {
  const [results,  setResults]  = useState([]);
  const [approval, setApproval] = useState(null);

  function handleResult(result) {
    setResults((prev) => [result, ...prev]);
    if (result.requires_human) {
      setApproval({ result, requestId: result.request_id || `req-${Date.now()}` });
    }
  }

  return (
    <div className="max-w-screen-lg mx-auto px-4 py-6 flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-white">Deploy Infrastructure</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Describe what you want in plain English. InfraGenie will plan, validate, and apply the Terraform configuration.
        </p>
      </div>

      <ChatInput onResult={handleResult} />

      {results.length === 0 && (
        <div className="text-center py-16 text-gray-700">
          <div className="text-4xl mb-3">⚡</div>
          <p className="text-sm">Submit a request above to see results here.</p>
        </div>
      )}

      <div className="space-y-4">
        {results.map((r, i) => (
          <AgentResultCard
            key={i}
            result={r}
            requestId={r.request_id}
            onApprove={(rid, res) => setApproval({ result: res, requestId: rid })}
          />
        ))}
      </div>

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
