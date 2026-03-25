import React, { useEffect, useMemo, useState } from "react";
import { getSystemHealth, type HealthPayload } from "@/lib/api";

type HealthState = "healthy" | "degraded" | "down";

interface ServiceHealth {
  name: string;
  status: HealthState;
  detail: string;
}

function normalizeStatus(raw: string | undefined): HealthState {
  const value = (raw ?? "").toLowerCase();
  if (value.includes("ok") || value.includes("healthy") || value === "pass") return "healthy";
  if (value.includes("degraded") || value.includes("warn")) return "degraded";
  return "down";
}

function statusStyle(status: HealthState): { color: string; bg: string } {
  if (status === "healthy") return { color: "#006b38", bg: "#e9f8ef" };
  if (status === "degraded") return { color: "#9a5100", bg: "#fff3df" };
  return { color: "#9b1c1c", bg: "#fdeceb" };
}

export default function SystemHealth() {
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [services, setServices] = useState<ServiceHealth[]>([
    { name: "API Gateway", status: "degraded", detail: "Waiting for first health poll." },
    { name: "PostgreSQL", status: "degraded", detail: "Waiting for first health poll." },
    { name: "Kafka", status: "degraded", detail: "Waiting for first health poll." },
  ]);

  useEffect(() => {
    let active = true;

    const fetchHealth = async () => {
      try {
        const body = (await getSystemHealth()) as HealthPayload;

        if (!active) return;

        const lagTotal =
          typeof body.kafka_lag === "object" && body.kafka_lag
            ? body.kafka_lag._summary?.total_lag
            : undefined;

        const next: ServiceHealth[] = [
          {
            name: "API Gateway",
            status: normalizeStatus(body.status),
            detail: "Health endpoint reachable.",
          },
          {
            name: "PostgreSQL",
            status: normalizeStatus(body.pg),
            detail: body.pg || "No detail returned.",
          },
          {
            name: "Kafka",
            status: normalizeStatus(body.kafka),
            detail:
              typeof lagTotal === "number"
                ? `${body.kafka || "No detail"} | Consumer lag: ${lagTotal}`
                : body.kafka || "No detail returned.",
          },
        ];

        setServices(next);
        setUpdatedAt(new Date().toLocaleTimeString());
        setMessage("Live data from /healthz?deep=true");
      } catch (error) {
        if (!active) return;
        const detail = error instanceof Error ? error.message : "Unknown error";
        setServices([
          { name: "API Gateway", status: "down", detail: `Health endpoint unavailable: ${detail}` },
          { name: "PostgreSQL", status: "down", detail: "Could not read database status." },
          { name: "Kafka", status: "down", detail: "Could not read kafka status." },
        ]);
        setUpdatedAt(new Date().toLocaleTimeString());
        setMessage("Using fallback down-state because live health request failed.");
      } finally {
        if (active) setLoading(false);
      }
    };

    fetchHealth();
    const timer = window.setInterval(fetchHealth, 10000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const overallStatus: HealthState = useMemo(() => {
    if (services.some((service) => service.status === "down")) return "down";
    if (services.some((service) => service.status === "degraded")) return "degraded";
    return "healthy";
  }, [services]);

  const overall = statusStyle(overallStatus);

  return (
    <section className="mi-page">
      <header>
        <h2 style={{ margin: 0 }}>System Health</h2>
        <p style={{ marginTop: 8 }}>
          Live infrastructure telemetry from backend health checks. Auto-refresh every 10 seconds.
        </p>
      </header>

      <div
        className="mi-card"
        style={{
          border: `1px solid ${overall.color}`,
          background: overall.bg,
        }}
      >
        <strong style={{ color: overall.color }}>Overall: {overallStatus.toUpperCase()}</strong>
        <div style={{ marginTop: 6, color: "#30475d", fontSize: 14 }}>
          {loading ? "Loading initial signal..." : `Last updated: ${updatedAt}`}
        </div>
        <div style={{ marginTop: 4, color: "#30475d", fontSize: 14 }}>{message}</div>
      </div>

      <div className="mi-list">
        {services.map((service) => {
          const style = statusStyle(service.status);
          return (
            <article key={service.name} className="mi-card" style={{ display: "grid", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>{service.name}</strong>
                <span className={`mi-status-chip ${service.status}`} style={{ color: style.color, background: style.bg }}>
                  {service.status.toUpperCase()}
                </span>
              </div>
              <p style={{ margin: 0, color: "#3f566c", fontSize: 14 }}>{service.detail}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
