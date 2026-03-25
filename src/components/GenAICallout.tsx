import React from "react";

type Tone = "info" | "success" | "warning";

export interface GenAICalloutProps {
  title: string;
  summary: string;
  confidence?: number;
  tone?: Tone;
  bullets?: string[];
  footer?: string;
}

const toneStyles: Record<Tone, { border: string; background: string; badge: string }> = {
  info: {
    border: "#0057b8",
    background: "rgba(0, 87, 184, 0.08)",
    badge: "#0057b8",
  },
  success: {
    border: "#007a3d",
    background: "rgba(0, 122, 61, 0.08)",
    badge: "#007a3d",
  },
  warning: {
    border: "#b35600",
    background: "rgba(179, 86, 0, 0.1)",
    badge: "#b35600",
  },
};

export default function GenAICallout({
  title,
  summary,
  confidence,
  tone = "info",
  bullets = [],
  footer,
}: GenAICalloutProps) {
  const style = toneStyles[tone];

  return (
    <aside
      className="mi-card"
      style={{
        border: `1px solid ${style.border}`,
        borderLeft: `6px solid ${style.border}`,
        background: style.background,
      }}
      aria-live="polite"
    >
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 16 }}>{title}</strong>
        <span
          style={{
            display: "inline-block",
            fontSize: 12,
            color: "#ffffff",
            background: style.badge,
            borderRadius: 999,
            padding: "4px 10px",
            letterSpacing: 0.2,
          }}
        >
          GenAI
        </span>
      </header>

      <p style={{ margin: "10px 0 0", color: "#1d2733", lineHeight: 1.5 }}>{summary}</p>

      {typeof confidence === "number" && (
        <p style={{ margin: "8px 0 0", color: "#253444", fontSize: 14 }}>
          Confidence: <strong>{Math.round(confidence)}%</strong>
        </p>
      )}

      {bullets.length > 0 && (
        <ul style={{ margin: "10px 0 0", paddingLeft: 20, color: "#243242" }}>
          {bullets.map((bullet) => (
            <li key={bullet} style={{ marginTop: 6 }}>
              {bullet}
            </li>
          ))}
        </ul>
      )}

      {footer && <p style={{ margin: "10px 0 0", fontSize: 13, color: "#33475b" }}>{footer}</p>}
    </aside>
  );
}
