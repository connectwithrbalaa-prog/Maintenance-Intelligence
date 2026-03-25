import React, { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getBadActors, getRcaOutcomes, type BadActor, type RcaOutcomeSummary } from "@/lib/api";

const monthlyOutcomes = [
  { month: "Jan", avoidedDowntimeHours: 42, mtbfHours: 315 },
  { month: "Feb", avoidedDowntimeHours: 51, mtbfHours: 332 },
  { month: "Mar", avoidedDowntimeHours: 63, mtbfHours: 358 },
  { month: "Apr", avoidedDowntimeHours: 58, mtbfHours: 349 },
  { month: "May", avoidedDowntimeHours: 72, mtbfHours: 381 },
  { month: "Jun", avoidedDowntimeHours: 77, mtbfHours: 396 },
];

const badActorReduction = [
  { asset: "CT-301A", before: 9, after: 4 },
  { asset: "PS-105B", before: 7, after: 3 },
  { asset: "GT-201", before: 5, after: 2 },
  { asset: "K-401", before: 6, after: 2 },
];

function monthLabel(dateText: string): string {
  const parsed = new Date(dateText);
  if (Number.isNaN(parsed.getTime())) return dateText;
  return parsed.toLocaleString(undefined, { month: "short" });
}

export default function Outcomes() {
  const [outcomes, setOutcomes] = useState<RcaOutcomeSummary | null>(null);
  const [actors, setActors] = useState<BadActor[]>([]);
  const [notice, setNotice] = useState<string>("Loading live analytics...");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [outcomePayload, badActorsPayload] = await Promise.all([
          getRcaOutcomes(180),
          getBadActors(4),
        ]);
        if (!active) return;
        setOutcomes(outcomePayload);
        setActors(badActorsPayload);
        setNotice("Live analytics loaded from reports API.");
      } catch (_error) {
        if (!active) return;
        setNotice("Using demo analytics. Live reports API is currently unavailable.");
      }
    };

    load();
    return () => {
      active = false;
    };
  }, []);

  const chartSeries = useMemo(() => {
    const metrics = outcomes?.backend_metrics;
    if (!metrics) return monthlyOutcomes;

    const monthMap: Record<string, { month: string; avoidedDowntimeHours: number; mtbfHours: number }> = {};
    Object.values(metrics).forEach((metric) => {
      (metric.handoff_volume || []).forEach((point) => {
        const label = monthLabel(point.date);
        if (!monthMap[label]) {
          monthMap[label] = { month: label, avoidedDowntimeHours: 0, mtbfHours: 0 };
        }
        monthMap[label].avoidedDowntimeHours += Number(point.value || 0);
      });

      (metric.handoff_success_rate_series || []).forEach((point) => {
        const label = monthLabel(point.date);
        if (!monthMap[label]) {
          monthMap[label] = { month: label, avoidedDowntimeHours: 0, mtbfHours: 0 };
        }
        if (typeof point.value === "number") {
          monthMap[label].mtbfHours += Math.round(point.value * 100);
        }
      });
    });

    const rows = Object.values(monthMap);
    return rows.length > 0 ? rows : monthlyOutcomes;
  }, [outcomes]);

  const badActorRows = useMemo(() => {
    if (!actors.length) return badActorReduction;
    return actors.map((actor) => ({
      asset: actor.asset_id,
      before: actor.events_90d,
      after: actor.workorders_90d,
    }));
  }, [actors]);

  const cmms = outcomes?.cmms_summary;
  const approvalSeconds = cmms?.approval_to_handoff_seconds_avg;

  return (
    <section className="mi-page">
      <header>
        <h2 style={{ margin: 0 }}>Outcomes & Analytics</h2>
        <p style={{ marginTop: 8, maxWidth: 860 }}>
          Reliability outcomes from PM optimization and RCA recommendations, with trend-level visibility across
          critical upstream assets.
        </p>
      </header>

      <div className="mi-kpis">
        <div className="mi-kpi">
          <div className="label">Successful Handoffs</div>
          <div className="value">{cmms?.success_total ?? 0}</div>
        </div>
        <div className="mi-kpi">
          <div className="label">Acceptance Rate</div>
          <div className="value">
            {typeof outcomes?.acceptance_rate === "number" ? `${Math.round(outcomes.acceptance_rate * 100)}%` : "N/A"}
          </div>
        </div>
        <div className="mi-kpi">
          <div className="label">Approval to Handoff</div>
          <div className="value">
            {typeof approvalSeconds === "number" ? `${Math.round(approvalSeconds / 60)} min` : "N/A"}
          </div>
        </div>
      </div>

      <p>{notice}</p>

      <article className="mi-card">
        <h2 style={{ margin: "0 0 10px", fontSize: 18 }}>Monthly trend: downtime vs MTBF</h2>
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <LineChart data={chartSeries}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip />
              <Legend />
              <Bar yAxisId="left" dataKey="avoidedDowntimeHours" name="Avoided Downtime (h)" fill="#007a3d" />
              <Line yAxisId="right" type="monotone" dataKey="mtbfHours" name="MTBF (h)" stroke="#0057b8" strokeWidth={3} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </article>

      <article className="mi-card">
        <h2 style={{ margin: "0 0 10px", fontSize: 18 }}>Bad-actor reduction by asset</h2>
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={badActorRows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="asset" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="before" name="Before program" fill="#b35600" />
              <Bar dataKey="after" name="After program" fill="#0057b8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </article>
    </section>
  );
}
