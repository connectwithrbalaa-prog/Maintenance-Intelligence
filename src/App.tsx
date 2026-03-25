import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppSidebar from "./components/AppSidebar";
import PmAdvisor from "./pages/PmAdvisor";
import Outcomes from "./pages/Outcomes";
import RunDetail from "./pages/RunDetail";
import SystemHealth from "./pages/SystemHealth";

export default function App() {
  return (
    <div className="mi-app-shell">
      <header className="mi-topbar">
        <p className="mi-kicker">Maintenance Intelligence</p>
        <h1 className="mi-title">Operations Command Center</h1>
      </header>

      <div className="mi-layout">
        <AppSidebar />

        <main className="mi-content">
          <Routes>
            <Route path="/pm-advisor" element={<PmAdvisor />} />
            <Route path="/outcomes" element={<Outcomes />} />
            <Route path="/system-health" element={<SystemHealth />} />
            {/* ── New routes ─────────────────────────────────────── */}
            <Route path="/runs" element={<RunDetail />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
            <Route path="*" element={<Navigate to="/runs" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
