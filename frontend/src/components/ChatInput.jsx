import React, { useState } from "react";
import { deployInfra } from "../api/client";

const PLACEHOLDER =
  "Describe the infrastructure you want… e.g. Create a scalable web app in AWS with a load balancer and RDS MySQL.";

export default function ChatInput({ onResult }) {
  const [input,   setInput]   = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setError(null);
    setLoading(true);
    try {
      const result = await deployInfra(trimmed);
      onResult?.(result);
      setInput("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Request failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-2 p-4 bg-gray-900 border border-gray-800 rounded-xl shadow-lg"
    >
      <label className="text-xs font-semibold text-gray-500 uppercase tracking-widest">
        Natural-language infrastructure request
      </label>

      <div className="flex gap-3 items-end">
        <textarea
          id="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          rows={3}
          disabled={loading}
          placeholder={PLACEHOLDER}
          className="input-field flex-1 resize-none"
        />
        <button
          type="submit"
          id="chat-submit-btn"
          disabled={loading || !input.trim()}
          className="btn-primary self-stretch px-6"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Planning…
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <span>⚡</span> Deploy
            </span>
          )}
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}
    </form>
  );
}
