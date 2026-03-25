import React, { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { api } from "@/lib/api";

type HealthStatus = "healthy" | "degraded" | "down" | "unknown";

const NAV_GROUPS = [
  {
    label: "Intelligence",
    items: [
      { to: "/pm-advisor", label: "PM Advisor" },
      { to: "/outcomes", label: "Outcomes" },
      { to: "/runs", label: "AI Runs" },
    ],
  },
  {
    label: "Platform",
    items: [
      { to: "/system-health", label: "System Health" },
      { to: "/signals", label: "Signals" },
    ],
  },
] as const;

function HealthDot({ status }: { status: HealthStatus }) {
  const colorMap: Record<HealthStatus, string> = {
    healthy: "#22c55e",
    degraded: "#f59e0b",
    down: "#ef4444",
    unknown: "#9ca3af",
  };
  return (
    <span
      aria-label={`System health: ${status}`}
      title={`System: ${status}`}
      style={{
        display: "inline-block",
        width: 9,
        height: 9,
        borderRadius: "50%",
        background: colorMap[status],
        flexShrink: 0,
        boxShadow: status === "healthy" ? "0 0 0 2px #bbf7d0" : undefined,
      }}
    />
  );
}

function resolveHealthStatus(status?: string): HealthStatus {
  if (!status) return "unknown";
  const s = status.toLowerCase();
  if (s === "ok" || s === "healthy") return "healthy";
  if (s === "degraded") return "degraded";
  return "down";
}

export default function AppSidebar() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("unknown");

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await api.getHealthDeep();
        if (!cancelled) {
          setHealthStatus(resolveHealthStatus(data.status));
        }
      } catch {
        if (!cancelled) setHealthStatus("down");
      }
    }

    poll();
    const intervalId = setInterval(poll, 30_000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  return (
    <aside className="mi-sidebar">
      <div className="mi-sidebar-brand">
        <span className="mi-sidebar-brand-text">MI</span>
        <HealthDot status={healthStatus} />
      </div>

      {NAV_GROUPS.map((group) => (
        <nav key={group.label} className="mi-nav-group" aria-label={group.label}>
          <p className="mi-nav-group-label">{group.label}</p>
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }: { isActive: boolean }) =>
                isActive ? "mi-sidebar-link active" : "mi-sidebar-link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ))}
    </aside>
  );
}
