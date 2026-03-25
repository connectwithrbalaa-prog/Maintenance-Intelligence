import React, { useEffect, useMemo, useState } from "react";
import { approvePmProposal, getPmProposals, type PmProposal } from "@/lib/api";
import GenAICallout from "../components/GenAICallout";

type LocalProposal = {
  id: string;
  equipment: string;
  summary: string;
  confidence: number;
  risk: "Low" | "Moderate" | "High";
  status: string;
  attemptsRemaining: number;
  retryAllowed: boolean;
};

const fallbackProposals: LocalProposal[] = [
  {
    id: "RUN-OG-COMP-001",
    equipment: "CT-301A Compressor Train",
    summary: "Reduce interval from 30 to 21 days based on bearing temperature drift and vibration trend.",
    confidence: 84,
    risk: "Moderate",
    status: "pending",
    attemptsRemaining: 2,
    retryAllowed: true,
  },
  {
    id: "RUN-OG-PUMP-002",
    equipment: "PS-105B Injection Pump",
    summary: "Advance seal-service inspection window to reduce leakage escalation events.",
    confidence: 81,
    risk: "Low",
    status: "pending",
    attemptsRemaining: 3,
    retryAllowed: true,
  },
  {
    id: "RUN-OG-TURB-003",
    equipment: "GT-201 Gas Turbine",
    summary: "Increase combustor inspection frequency due to instability signature in recent runs.",
    confidence: 76,
    risk: "High",
    status: "pending",
    attemptsRemaining: 1,
    retryAllowed: true,
  },
];

function normalizeRisk(confidence: number): LocalProposal["risk"] {
  if (confidence >= 85) return "High";
  if (confidence >= 70) return "Moderate";
  return "Low";
}

function toLocal(proposal: PmProposal): LocalProposal {
  const confidence = typeof proposal.confidence === "number" ? proposal.confidence : 72;
  return {
    id: proposal.proposal_id,
    equipment: proposal.asset_id || proposal.title || "Unknown asset",
    summary: proposal.rationale || proposal.title || "No rationale available.",
    confidence,
    risk: normalizeRisk(confidence),
    status: proposal.status || "pending",
    attemptsRemaining: typeof proposal.attempts_remaining === "number" ? proposal.attempts_remaining : 0,
    retryAllowed: proposal.retry_allowed !== false,
  };
}

export default function PmAdvisor() {
  const [selectedId, setSelectedId] = useState<string>(fallbackProposals[0].id);
  const [proposals, setProposals] = useState<LocalProposal[]>(fallbackProposals);
  const [loading, setLoading] = useState<boolean>(true);
  const [busy, setBusy] = useState<boolean>(false);
  const [notice, setNotice] = useState<string>("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await getPmProposals();
        if (!active || data.length === 0) return;
        const normalized = data.map(toLocal);
        setProposals(normalized);
        setSelectedId((current) => normalized.some((proposal) => proposal.id === current) ? current : normalized[0].id);
      } catch (_error) {
        setNotice("Using local demo data. Live PM proposal API is currently unavailable.");
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    return () => {
      active = false;
    };
  }, []);

  const selected = useMemo(
    () => proposals.find((proposal) => proposal.id === selectedId) ?? proposals[0] ?? fallbackProposals[0],
    [selectedId, proposals]
  );

  const approveSelected = async () => {
    setBusy(true);
    try {
      const response = await approvePmProposal(selected.id);
      const updatedStatus = response.status || "approved";
      setProposals((current) =>
        current.map((proposal) =>
          proposal.id === selected.id
            ? {
                ...proposal,
                status: updatedStatus,
                retryAllowed: false,
              }
            : proposal
        )
      );
      setNotice(response.detail || "Proposal approved and handed off.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Approval failed";
      setNotice(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mi-page">
      <header>
        <h2 style={{ margin: 0 }}>PM Advisor</h2>
        <p style={{ marginTop: 8, maxWidth: 880 }}>
          Review GenAI maintenance interval recommendations based on equipment history, ISO failure patterns,
          and observed downtime impact.
        </p>
      </header>

      <div className="mi-grid-2">
        <aside className="mi-card">
          <h2>Proposal Queue</h2>
          <div className="mi-list">
            {proposals.map((proposal) => {
              const active = proposal.id === selected.id;
              return (
                <button
                  key={proposal.id}
                  onClick={() => setSelectedId(proposal.id)}
                  className={active ? "mi-btn active" : "mi-btn"}
                  style={{ textAlign: "left", width: "100%" }}
                >
                  <div style={{ fontWeight: 600 }}>{proposal.equipment}</div>
                  <div style={{ fontSize: 13, color: "#4c5d70", marginTop: 4 }}>
                    {proposal.id} | Risk: {proposal.risk} | Status: {proposal.status}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <main className="mi-list">
          <article className="mi-card">
            <h2>{selected.equipment}</h2>
            <div className="mi-kpis">
              <div className="mi-kpi">
                <div className="label">Confidence</div>
                <div className="value">{Math.round(selected.confidence)}%</div>
              </div>
              <div className="mi-kpi">
                <div className="label">Attempts Remaining</div>
                <div className="value">{selected.attemptsRemaining}</div>
              </div>
              <div className="mi-kpi">
                <div className="label">Current State</div>
                <div className="value" style={{ fontSize: 20 }}>{selected.status}</div>
              </div>
            </div>

            <p style={{ marginTop: 14, marginBottom: 0 }}>
              Reliability risk: <strong>{selected.risk}</strong>
            </p>
          </article>

          <GenAICallout
            title="AI Recommendation"
            summary={selected.summary}
            confidence={selected.confidence}
            tone={selected.risk === "High" ? "warning" : "success"}
            bullets={[
              "Signal drift in vibration and bearing temperature over last 3 cycles.",
              "Failure mode correlation matches ISO rotating equipment degradation pattern.",
              "Expected labor increase is offset by lower unplanned shutdown impact.",
            ]}
            footer="Generated from maintenance events, failure taxonomy, and trend analytics."
          />

          <div className="mi-actions">
            <button
              type="button"
              disabled={busy || !selected.retryAllowed}
              onClick={approveSelected}
              className="mi-btn mi-btn-primary"
            >
              {busy ? "Submitting approval..." : "Approve proposal"}
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mi-btn"
            >
              Refresh proposals
            </button>
          </div>

          <p style={{ margin: 0 }}>
            {loading ? "Loading PM proposals..." : notice || "Review and approve proposals for CMMS handoff."}
          </p>
        </main>
      </div>
    </section>
  );
}
