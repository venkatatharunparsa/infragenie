import React from "react";
import CostWidget from "../components/CostWidget";
import InfraMap from "../components/InfraMap";

export default function MonitorPage() {
  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-white">Monitor</h1>
        <p className="text-xs text-gray-500 mt-0.5">Live AWS resource inventory and cost tracking</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <CostWidget />
        <InfraMap />
      </div>
    </div>
  );
}
