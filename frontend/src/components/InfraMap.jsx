import React, { useEffect, useState } from "react";
import { getResources } from "../api/client";

const STATUS_DOT = {
  running:   "bg-green-500",
  stopped:   "bg-red-500",
  available: "bg-green-500",
  deleting:  "bg-orange-500",
};

function statusDot(status) {
  const s = (status || "unknown").toLowerCase();
  return STATUS_DOT[s] || "bg-gray-600";
}

function ResourceSection({ title, items, renderRow }) {
  if (!items?.length) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">
        {title} <span className="text-gray-700">({items.length})</span>
      </h3>
      <div className="space-y-1">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex items-center gap-2 text-xs py-1 px-2 rounded-lg hover:bg-gray-800 transition-colors"
          >
            {renderRow(item)}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function InfraMap() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await getResources();
      setData(res);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const total =
    (data?.ec2_instances?.length || 0) +
    (data?.rds_instances?.length || 0) +
    (data?.s3_buckets?.length    || 0) +
    (data?.lambda_functions?.length || 0);

  return (
    <div className="card flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300">
          Infrastructure Resources
          {!loading && data && (
            <span className="ml-2 text-xs text-gray-600">({total} total)</span>
          )}
        </h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-40"
        >
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>

      {loading && (
        <div className="text-xs text-gray-600 animate-pulse">Fetching resources…</div>
      )}

      {error && (
        <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {!loading && !error && data && (
        <div className="space-y-4">
          <ResourceSection
            title="EC2 Instances"
            items={data.ec2_instances}
            renderRow={(r) => (
              <>
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot(r.state)}`} />
                <span className="text-gray-200 font-mono">{r.instance_id}</span>
                <span className="text-gray-500">{r.instance_type}</span>
                {r.name && <span className="text-gray-600">({r.name})</span>}
                <span className={`ml-auto text-gray-500 ${statusDot(r.state) === "bg-green-500" ? "text-green-500" : "text-red-500"}`}>
                  {r.state || "unknown"}
                </span>
              </>
            )}
          />
          <ResourceSection
            title="RDS Instances"
            items={data.rds_instances}
            renderRow={(r) => (
              <>
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot(r.status)}`} />
                <span className="text-gray-200 font-mono">{r.db_identifier}</span>
                <span className="text-gray-500">{r.engine}</span>
                <span className="ml-auto text-gray-500">{r.status}</span>
              </>
            )}
          />
          <ResourceSection
            title="S3 Buckets"
            items={data.s3_buckets}
            renderRow={(r) => (
              <>
                <span className="w-2 h-2 rounded-full flex-shrink-0 bg-blue-500" />
                <span className="text-gray-200">{r.name}</span>
              </>
            )}
          />
          <ResourceSection
            title="Lambda Functions"
            items={data.lambda_functions}
            renderRow={(r) => (
              <>
                <span className="w-2 h-2 rounded-full flex-shrink-0 bg-violet-500" />
                <span className="text-gray-200">{r.name}</span>
                <span className="text-gray-500">{r.runtime}</span>
                <span className="ml-auto text-gray-600">{r.memory_mb} MB</span>
              </>
            )}
          />
          {total === 0 && (
            <p className="text-xs text-gray-600 italic text-center">No resources found.</p>
          )}
        </div>
      )}
    </div>
  );
}
