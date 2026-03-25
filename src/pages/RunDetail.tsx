import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { RunDetailFull, RunSummary } from "../lib/api";
import { getPortalRuns, getRunDetail, submitFeedback } from "../lib/api";

// ── Typewriter hook ────────────────────────────────────────────────────────────

function useTypewriter(text: string, speedMs = 16): string {
  const [displayed, setDisplayed] = useState("");
  const prevTextRef = useRef("");

  useEffect(() => {
    if (!text) {
      setDisplayed("");
      prevTextRef.current = "";
      return;
    }
    // Reset animation whenever source text changes
    setDisplayed("");
    prevTextRef.current = text;
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, speedMs);
    return () => clearInterval(id);
  }, [text, speedMs]);

  return displayed;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ConfidenceBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return null;
  const pct = score > 1 ? Math.round(score) : Math.round(score * 100);
  const bg = pct >= 80 ? "#d1fae5" : pct >= 65 ? "#fef3c7" : "#fee2e2";
  const color = pct >= 80 ? "#065f46" : pct >= 65 ? "#92400e" : "#7f1d1d";
  return (
    <span
      style={{
        background: bg,
        color,
        borderRadius: 4,
        padding: "2px 10px",
        fontSize: 13,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {pct}% confidence
    </span>
  );
}

function ModelInfoPanel({ model }: { model: RunSummary["model"] }) {
  if (!model) return null;
  const pct =
    model.confidence !== null && model.confidence !== undefined
      ? model.confidence > 1
        ? model.confidence.toFixed(1)
        : (model.confidence * 100).toFixed(1)
      : null;

  return (
    <dl
      style={{
        display: "flex",
        gap: "4px 24px",
        flexWrap: "wrap",
        margin: "8px 0 0",
        fontSize: 12,
        color: "#6b7280",
      }}
    >
      {model.name && (
        <>
          <dt style={{ fontWeight: 600, color: "#374151" }}>Model</dt>
          <dd style={{ margin: 0 }}>
            {model.name}
            {model.version ? ` · ${model.version}` : ""}
          </dd>
        </>
      )}
      {model.latency_ms !== null && model.latency_ms !== undefined && (
        <>
          <dt style={{ fontWeight: 600, color: "#374151" }}>Latency</dt>
          <dd style={{ margin: 0 }}>{model.latency_ms.toFixed(0)} ms</dd>
        </>
      )}
      {pct !== null && (
        <>
          <dt style={{ fontWeight: 600, color: "#374151" }}>Model conf.</dt>
          <dd style={{ margin: 0 }}>{pct}%</dd>
        </>
      )}
    </dl>
  );
}

function FeedbackBar({
  runId,
  recommendationId,
  onDone,
}: {
  runId: string;
  recommendationId?: string;
  onDone: (action: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function send(action: "accept" | "reject" | "edited") {
    setBusy(true);
    setNotice(null);
    try {
      await submitFeedback({ run_id: runId, recommendation_id: recommendationId, action });
      setNotice(`Feedback "${action}" recorded.`);
      onDone(action);
    } catch (e: unknown) {
      setNotice(e instanceof Error ? e.message : "Feedback submission failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mi-actions" style={{ marginTop: 16 }}>
      <span style={{ fontSize: 13, color: "#6b7280", marginRight: 8 }}>Was this helpful?</span>
      <button className="mi-btn mi-btn-primary" disabled={busy} onClick={() => send("accept")}>
        ✓ Accept
      </button>
      <button className="mi-btn" disabled={busy} onClick={() => send("reject")}>
        ✗ Reject
      </button>
      <button className="mi-btn" disabled={busy} onClick={() => send("edited")}>
        ✎ Edited
      </button>
      {notice && (
        <span style={{ marginLeft: 12, fontSize: 13, color: "#6b7280" }}>{notice}</span>
      )}
    </div>
  );
}

function RunCard({ run, onClick }: { run: RunSummary; onClick: () => void }) {
  const pct =
    run.confidence !== null && run.confidence !== undefined
      ? run.confidence > 1
        ? Math.round(run.confidence)
        : Math.round(run.confidence * 100)
      : null;

  return (
    <button
      className="mi-card"
      onClick={onClick}
      style={{
        cursor: "pointer",
        textAlign: "left",
        width: "100%",
        border: "1px solid #e5e7eb",
        background: "var(--mi-panel)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 8,
        }}
      >
        <strong style={{ fontSize: 14 }}>{run.title || run.run_id}</strong>
        {pct !== null && (
          <span
            style={{
              fontSize: 12,
              background: pct >= 80 ? "#d1fae5" : pct >= 65 ? "#fef3c7" : "#fee2e2",
              color: pct >= 80 ? "#065f46" : pct >= 65 ? "#92400e" : "#7f1d1d",
              borderRadius: 4,
              padding: "1px 6px",
              whiteSpace: "nowrap",
            }}
          >
            {pct}%
          </span>
        )}
      </div>
      <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
        {run.summary
          ? `${run.summary.slice(0, 120)}${run.summary.length > 120 ? "…" : ""}`
          : "—"}
      </p>
      <p style={{ margin: "4px 0 0", fontSize: 12, color: "#9ca3af" }}>
        {run.date} · {run.run_id}
      </p>
    </button>
  );
}

// ── Demo fallback ─────────────────────────────────────────────────────────────

const DEMO_RUNS: RunSummary[] = [
  {
    run_id: "RUN-OG-COMP-001",
    status: "completed",
    title: "CT-301A Bearing Degradation",
    summary:
      "Stage-2 bearing vibration exceeds ISO 10816-3 limit at 7.2 mm/s RMS. Lube oil supply temp trending +12°C above baseline. Root cause: lubrication starvation from partially blocked oil jet.",
    confidence: 0.89,
    model: { name: "gpt-4o", version: "2024-11", latency_ms: 4230, confidence: 0.89 },
    date: "2026-03-21",
    source_file: "RUN-OG-COMP-001.json",
    updated_at: Date.now() / 1000,
    recommendation_id: "REC-comp-001",
    immediate_actions: ["Reduce compressor load to 60%", "Inspect lube oil filter element"],
    pm_suggestions: ["Schedule bearing replacement within 72 h", "Flush lube oil circuit"],
  },
  {
    run_id: "RUN-OG-PUMP-002",
    status: "completed",
    title: "PS-105B Mechanical Seal Leak",
    summary:
      "Seal flush flow dropped 40% over 3 days. Shaft vibration at 1× BPF elevated to 4.1 mm/s. Probable cause: premature seal face wear from process fluid contamination.",
    confidence: 0.84,
    model: { name: "gpt-4o", version: "2024-11", latency_ms: 3810, confidence: 0.84 },
    date: "2026-03-21",
    source_file: "RUN-OG-PUMP-002.json",
    updated_at: Date.now() / 1000,
    recommendation_id: "REC-pump-002",
    immediate_actions: ["Increase seal flush pressure to 3.5 bar", "Prepare seal replacement kit"],
    pm_suggestions: ["Replace mechanical seal assembly during next scheduled window"],
  },
  {
    run_id: "RUN-OG-TURB-003",
    status: "completed",
    title: "GT-201 Combustion Imbalance",
    summary:
      "EGT spread delta 58°C against 35°C allowable. Fuel control valve response degraded to 220 ms. Contributing factor: fuel nozzle fouling causing uneven fuel distribution.",
    confidence: 0.76,
    model: { name: "gpt-4o", version: "2024-11", latency_ms: 4510, confidence: 0.76 },
    date: "2026-03-21",
    source_file: "RUN-OG-TURB-003.json",
    updated_at: Date.now() / 1000,
    recommendation_id: "REC-turb-003",
    immediate_actions: ["Reduce load to 80% power", "Monitor EGT spread every 2 h"],
    pm_suggestions: ["Schedule combustion inspection within 48 h"],
  },
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RunDetail() {
  const { runId } = useParams<{ runId?: string }>();
  const navigate = useNavigate();

  // ── List state ──────────────────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listDemo, setListDemo] = useState(false);

  // ── Detail state ────────────────────────────────────────────────────────────
  const [detail, setDetail] = useState<RunDetailFull | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailDemo, setDetailDemo] = useState(false);
  const [feedbackAction, setFeedbackAction] = useState<string | null>(null);

  // ── Load run list ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (runId) return;
    setListLoading(true);
    setListDemo(false);
    getPortalRuns(12)
      .then((data) => {
        if (data.length > 0) {
          setRuns(data);
        } else {
          setRuns(DEMO_RUNS);
          setListDemo(true);
        }
      })
      .catch(() => {
        setRuns(DEMO_RUNS);
        setListDemo(true);
      })
      .finally(() => setListLoading(false));
  }, [runId]);

  // ── Load run detail ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!runId) return;
    setDetailLoading(true);
    setDetail(null);
    setDetailDemo(false);
    setFeedbackAction(null);
    getRunDetail(runId)
      .then((data) => setDetail(data))
      .catch(() => {
        const fallback = DEMO_RUNS.find((r) => r.run_id === runId);
        if (fallback) {
          setDetail(fallback as RunDetailFull);
          setDetailDemo(true);
        }
      })
      .finally(() => setDetailLoading(false));
  }, [runId]);

  const summaryText = detail?.summary ?? "";
  const animatedSummary = useTypewriter(summaryText);

  // ── List view ───────────────────────────────────────────────────────────────
  if (!runId) {
    return (
      <div className="mi-page">
        <h2 style={{ margin: "0 0 4px" }}>AI Runs</h2>
        <p style={{ color: "#6b7280", fontSize: 14, margin: "0 0 16px" }}>
          Recent RCA analysis outputs from the intelligence layer
        </p>

        {listDemo && (
          <div
            className="mi-card"
            style={{
              background: "#fffbeb",
              borderLeft: "3px solid #f59e0b",
              marginBottom: 12,
            }}
          >
            <p style={{ margin: 0, fontSize: 13 }}>Using local demo data — API unavailable</p>
          </div>
        )}

        {listLoading ? (
          <p style={{ color: "#9ca3af", fontSize: 14 }}>Loading runs…</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {runs.map((run) => (
              <li key={run.run_id}>
                <RunCard run={run} onClick={() => navigate(`/runs/${run.run_id}`)} />
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // ── Detail view ─────────────────────────────────────────────────────────────
  return (
    <div className="mi-page">
      <button
        className="mi-btn"
        onClick={() => navigate("/runs")}
        style={{ marginBottom: 16 }}
      >
        ← Back to Runs
      </button>

      {detailLoading && (
        <p style={{ color: "#9ca3af", fontSize: 14 }}>Loading run detail…</p>
      )}

      {!detailLoading && !detail && (
        <div className="mi-card">
          <p style={{ margin: 0 }}>Run not found: <code>{runId}</code></p>
        </div>
      )}

      {detail && (
        <>
          {detailDemo && (
            <div
              className="mi-card"
              style={{
                background: "#fffbeb",
                borderLeft: "3px solid #f59e0b",
                marginBottom: 12,
              }}
            >
              <p style={{ margin: 0, fontSize: 13 }}>Using local demo data — API unavailable</p>
            </div>
          )}

          {/* ── Primary card ─────────────────────────────────────── */}
          <div className="mi-card">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <h2 style={{ margin: 0 }}>{detail.title || detail.run_id}</h2>
              <ConfidenceBadge score={detail.confidence} />
            </div>

            <ModelInfoPanel model={detail.model} />

            {/* Typewriter summary */}
            <p
              style={{
                marginTop: 16,
                lineHeight: 1.65,
                fontSize: 15,
                minHeight: "3em",
              }}
            >
              {animatedSummary || <span style={{ color: "#9ca3af" }}>…</span>}
            </p>

            {feedbackAction ? (
              <p style={{ marginTop: 12, fontSize: 13, color: "#6b7280" }}>
                Feedback recorded:{" "}
                <strong style={{ color: "#374151" }}>{feedbackAction}</strong>
              </p>
            ) : (
              <FeedbackBar
                runId={detail.run_id}
                recommendationId={detail.recommendation_id}
                onDone={setFeedbackAction}
              />
            )}
          </div>

          {/* ── Structured analysis ───────────────────────────────── */}
          {(detail.structured?.root_causes?.length ||
            detail.structured?.hypothesis?.length ||
            detail.structured?.contributing_factors?.length) ? (
            <div className="mi-card" style={{ marginTop: 12 }}>
              <h3 style={{ marginTop: 0 }}>Analysis</h3>

              {!!detail.structured?.root_causes?.length && (
                <>
                  <p style={{ fontWeight: 600, margin: "0 0 4px", fontSize: 14 }}>Root Causes</p>
                  <ul style={{ margin: "0 0 12px", paddingLeft: 20 }}>
                    {detail.structured.root_causes.map((c, i) => (
                      <li key={i} style={{ fontSize: 14 }}>
                        {c}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {!!detail.structured?.hypothesis?.length && (
                <>
                  <p style={{ fontWeight: 600, margin: "0 0 4px", fontSize: 14 }}>Hypothesis</p>
                  <ul style={{ margin: "0 0 12px", paddingLeft: 20 }}>
                    {detail.structured.hypothesis.map((h, i) => (
                      <li key={i} style={{ fontSize: 14 }}>
                        {h}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {!!detail.structured?.contributing_factors?.length && (
                <>
                  <p style={{ fontWeight: 600, margin: "0 0 4px", fontSize: 14 }}>
                    Contributing Factors
                  </p>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {detail.structured.contributing_factors.map((f, i) => (
                      <li key={i} style={{ fontSize: 14 }}>
                        {f}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          ) : null}

          {/* ── Immediate actions ─────────────────────────────────── */}
          {!!detail.immediate_actions?.length && (
            <div className="mi-card" style={{ marginTop: 12 }}>
              <h3 style={{ marginTop: 0 }}>Immediate Actions</h3>
              <ol style={{ margin: 0, paddingLeft: 20 }}>
                {detail.immediate_actions.map((a, i) => (
                  <li key={i} style={{ fontSize: 14, marginBottom: 4 }}>
                    {a}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* ── PM suggestions ────────────────────────────────────── */}
          {!!detail.pm_suggestions?.length && (
            <div className="mi-card" style={{ marginTop: 12 }}>
              <h3 style={{ marginTop: 0 }}>PM Suggestions</h3>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {detail.pm_suggestions.map((s, i) => (
                  <li key={i} style={{ fontSize: 14, marginBottom: 4 }}>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Repair plan ───────────────────────────────────────── */}
          {detail.repair_plan && (
            <div className="mi-card" style={{ marginTop: 12 }}>
              <h3 style={{ marginTop: 0 }}>Repair Plan</h3>
              {detail.repair_plan.summary && (
                <p style={{ fontSize: 14, margin: "0 0 8px" }}>{detail.repair_plan.summary}</p>
              )}
              <div
                style={{
                  display: "flex",
                  gap: 24,
                  flexWrap: "wrap",
                  fontSize: 13,
                  color: "#6b7280",
                }}
              >
                {detail.repair_plan.estimated_duration_hrs !== undefined &&
                  detail.repair_plan.estimated_duration_hrs !== null && (
                    <span>
                      <strong style={{ color: "#374151" }}>Duration:</strong>{" "}
                      {detail.repair_plan.estimated_duration_hrs} h
                    </span>
                  )}
                {detail.repair_plan.permit_type && (
                  <span>
                    <strong style={{ color: "#374151" }}>Permit:</strong>{" "}
                    {detail.repair_plan.permit_type}
                  </span>
                )}
                {detail.repair_plan.status && (
                  <span>
                    <strong style={{ color: "#374151" }}>Status:</strong>{" "}
                    {detail.repair_plan.status}
                  </span>
                )}
              </div>
              {!!detail.repair_plan.safety_requirements?.length && (
                <>
                  <p style={{ fontWeight: 600, margin: "12px 0 4px", fontSize: 14 }}>
                    Safety Requirements
                  </p>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {detail.repair_plan.safety_requirements.map((r, i) => (
                      <li key={i} style={{ fontSize: 13 }}>
                        {r}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
