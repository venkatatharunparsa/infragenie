import React, { useEffect, useRef, useState } from "react";

const WS_URL =
  (process.env.REACT_APP_WS_URL || "ws://localhost:8000") + "/ws";

const MAX_ENTRIES = 100;

const SEV_COLOR = {
  critical: "text-red-400",
  high:     "text-orange-400",
  medium:   "text-yellow-400",
  low:      "text-blue-400",
  info:     "text-gray-400",
};

export default function LiveLogFeed({ onNewResult }) {
  const [entries,   setEntries]   = useState([]);
  const [connected, setConnected] = useState(false);
  const [error,     setError]     = useState(null);
  const bottomRef = useRef(null);
  const wsRef     = useRef(null);

  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          setConnected(true);
          setError(null);
        };

        ws.onclose = () => {
          setConnected(false);
          // Auto-reconnect after 3 s
          setTimeout(connect, 3000);
        };

        ws.onerror = () => {
          setError("WebSocket connection error — retrying…");
          ws.close();
        };

        ws.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.type === "agent_result" && msg.payload) {
              const entry = { ...msg.payload, _id: Date.now() + Math.random() };
              setEntries((prev) => {
                const next = [...prev, entry];
                return next.length > MAX_ENTRIES ? next.slice(-MAX_ENTRIES) : next;
              });
              onNewResult?.(msg.payload);
            } else if (msg.type === "terraform_log") {
              // Terraform streaming log line
              const entry = {
                _id:       Date.now() + Math.random(),
                agent:     msg.label || "terraform",
                severity:  "info",
                finding:   msg.line,
                timestamp: msg.timestamp,
                _isLog:    true,
              };
              setEntries((prev) => {
                const next = [...prev, entry];
                return next.length > MAX_ENTRIES ? next.slice(-MAX_ENTRIES) : next;
              });
            }
          } catch {
            /* ignore malformed frames */
          }
        };
      } catch (err) {
        setError("Failed to create WebSocket.");
      }
    }

    connect();
    return () => wsRef.current?.close();
  }, [onNewResult]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  return (
    <div className="card flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <h2 className="text-sm font-semibold text-gray-300">Live Agent Feed</h2>
        <span className="flex items-center gap-1.5 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-green-500 animate-pulse" : "bg-gray-600"
            }`}
          />
          {connected ? "Connected" : "Reconnecting…"}
        </span>
      </div>

      {error && (
        <p className="text-xs text-red-400 mb-2 flex-shrink-0">{error}</p>
      )}

      {/* Feed */}
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        {entries.length === 0 ? (
          <p className="text-xs text-gray-600 italic mt-4 text-center">
            Waiting for agent events…
          </p>
        ) : (
          entries.map((e) => (
            <div
              key={e._id}
              className={`flex gap-2 items-start text-xs py-1 border-b border-gray-800 last:border-0 ${
                e._isLog ? "opacity-60" : ""
              }`}
            >
              {/* Timestamp */}
              <span className="text-gray-600 tabular-nums flex-shrink-0 w-20 truncate">
                {e.timestamp
                  ? new Date(e.timestamp).toLocaleTimeString()
                  : "—"}
              </span>

              {/* Agent */}
              <span className="text-blue-400 font-mono flex-shrink-0 w-20 truncate">
                {e.agent}
              </span>

              {/* Severity */}
              <span
                className={`font-semibold flex-shrink-0 w-16 ${
                  SEV_COLOR[(e.severity || "info").toLowerCase()] || "text-gray-400"
                }`}
              >
                {(e.severity || "INFO").toUpperCase()}
              </span>

              {/* Finding */}
              <span className="text-gray-300 flex-1 break-words">
                {e.finding}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
