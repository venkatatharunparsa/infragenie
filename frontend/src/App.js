import React from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import DeployPage from "./pages/DeployPage";
import MonitorPage from "./pages/MonitorPage";
import AuditLog from "./pages/AuditLog";

const NAV = [
  { to: "/",        label: "Dashboard" },
  { to: "/deploy",  label: "Deploy"    },
  { to: "/monitor", label: "Monitor"   },
  { to: "/audit",   label: "Audit Log" },
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex flex-col min-h-screen bg-gray-950">
        {/* ── Top navbar ───────────────────────────────────────────────── */}
        <header className="sticky top-0 z-50 bg-gray-900 border-b border-gray-800 shadow-lg">
          <div className="max-w-screen-xl mx-auto px-4 h-14 flex items-center gap-8">
            {/* Logo */}
            <div className="flex items-center gap-2 select-none">
              <span className="text-blue-500 text-xl">⚡</span>
              <span className="text-white font-bold text-lg tracking-tight">
                Infra<span className="text-blue-500">Genie</span>
              </span>
            </div>

            {/* Nav links */}
            <nav className="flex items-center gap-1">
              {NAV.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded-md text-sm font-medium transition-colors duration-150 ${
                      isActive
                        ? "bg-blue-600 text-white"
                        : "text-gray-400 hover:text-white hover:bg-gray-800"
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>

            {/* Right slot — status dot */}
            <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              Live
            </div>
          </div>
        </header>

        {/* ── Page content ─────────────────────────────────────────────── */}
        <main className="flex-1">
          <Routes>
            <Route path="/"        element={<Dashboard />}  />
            <Route path="/deploy"  element={<DeployPage />} />
            <Route path="/monitor" element={<MonitorPage />}/>
            <Route path="/audit"   element={<AuditLog />}   />
          </Routes>
        </main>

        {/* ── Footer ───────────────────────────────────────────────────── */}
        <footer className="py-3 text-center text-xs text-gray-700 border-t border-gray-900">
          InfraGenie · AI-Powered Infrastructure Management
        </footer>
      </div>
    </BrowserRouter>
  );
}
