// VITE_API_BASE_URL is set in Lovable's environment variable settings
// (Project Settings → Environment Variables → VITE_API_BASE_URL=https://yourdomain.com)
// For local dev it falls back to the dev proxy.
const API_BASES: string[] = import.meta.env.VITE_API_BASE_URL
  ? [import.meta.env.VITE_API_BASE_URL as string]
  : ["/backend"];

const headers: HeadersInit = {
  "x-dev-user": "admin",
  "Content-Type": "application/json",
  getHealthDeep: async () => apiFetch<any>("/healthz?deep=true"),
  getOutcomes: async (window = 30) => apiFetch<any>(`/api/v1/reports/rca-outcomes?window=${window}`),
  getBadActors: async (limit = 5) => apiFetch<any[]>(`/api/v1/reports/bad-actors?limit=${limit}`),
  getSignalsSummary: async (assetId: string) => apiFetch<any>(`/api/v1/signals/summary?asset_id=${assetId}`),
  analyzePm: async (body: object) => apiFetch<any>("/api/v1/agents/pm/advisor/analyze", { method: "POST", body: JSON.stringify(body) }),
  approvePmProposal: async (id: string) => apiFetch<any>(`/api/v1/agents/pm/proposals/${id}/approve`, { method: "POST" }),
  submitFeedback: async (body: object) => apiFetch<any>("/api/v1/feedback", { method: "POST", body: JSON.stringify(body) }),
};

async function apiFetch<T>(path: string): Promise<T> {
  let lastError: unknown;

  for (const base of API_BASES) {
    try {
      const res = await fetch(`${base}${path}`, { headers });
      if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
      }

      const contentType = res.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        throw new Error("Non-JSON response received from API");
      }

      return (await res.json()) as T;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError ?? new Error("Unable to reach API");
}

// Raw API response shape
interface RawRun {
  run_id: string;
  status: string;
  event_id?: string;
  title: string;
  summary: string;
  confidence: number;
  hypothesis?: string[];
  immediate_actions?: string[];
  pm_suggestions?: string[];
  model?: Record<string, unknown>;
  context_meta?: {
    asset_id?: string;
    severity?: string;
    site_id?: string;
    [key: string]: unknown;
  };
  date?: string;
  [key: string]: unknown;
}

export interface RcaRun {
  id: string;
  asset_id: string;
  severity: string;
  summary: string;
  confidence_score: number;
  created_at: string;
  status: string;
  findings?: string[];
  recommendations?: string[];
  pm_suggestions?: string[];
  model_info?: Record<string, unknown>;
  context_metadata?: Record<string, unknown>;
  title?: string;
  [key: string]: unknown;
}

export interface HierarchyNode {
  id: string;
  name: string;
  type: string;
  children?: HierarchyNode[];
  [key: string]: unknown;
}

export interface FailureEvent {
  id: string;
  asset_id: string;
  failure_mode: string;
  severity: string;
  downtime_hours: number;
  date: string;
  [key: string]: unknown;
}

// ── Rich demo dataset ──────────────────────────────────────────────
const FALLBACK_RUNS: RawRun[] = [
  {
    run_id: "RCA-2026-0401",
    status: "completed",
    event_id: "EVT-COMP-5201",
    title: "Compressor Vibration Drift — COMP-220",
    summary:
      "Vibration envelope exceeded baseline by 18% over 36 hrs. Bearing inner-race defect frequency detected at 142 Hz. Immediate bearing inspection recommended before next production window.",
    confidence: 0.89,
    hypothesis: [
      "Bearing inner-race spalling causing radial vibration increase",
      "Potential rotor imbalance from coupler wear",
      "Lubrication film breakdown at elevated temperatures",
    ],
    immediate_actions: [
      "Increase vibration monitoring to every 2 hours",
      "Prepare standby compressor COMP-221 for switchover",
      "Collect oil sample for particle analysis",
    ],
    pm_suggestions: [
      "Create priority work order WO-4891 for bearing inspection",
      "Review lubrication schedule — last change was 420 hrs ago",
      "Order SKF 6320-2RS bearing set from warehouse",
    ],
    context_meta: { asset_id: "COMP-220", site_id: "PLANT-GULF-01", severity: "critical" },
    date: "2026-03-22",
  },
  {
    run_id: "RCA-2026-0398",
    status: "completed",
    event_id: "EVT-SEAL-7203",
    title: "Seal Oil Pressure Drop — Pump PS-105B",
    summary:
      "Seal oil differential pressure dropped 22% over 48 hrs. Process-fluid traces detected in return stream indicating early-stage mechanical seal wear. Plan replacement within 72 hrs.",
    confidence: 0.84,
    hypothesis: [
      "Mechanical seal face wear allowing fluid ingress",
      "Suspended solids from upstream filter bypass accelerating erosion",
    ],
    immediate_actions: [
      "Increase seal oil monitoring to every 2 hours",
      "Confirm standby pump PS-105C readiness",
      "Install temporary inline filter on seal oil supply",
    ],
    pm_suggestions: [
      "Plan seal cartridge replacement during next turnaround",
      "Verify spare John Crane Type 2800 seal in warehouse",
      "Review upstream strainer mesh size",
    ],
    context_meta: { asset_id: "PS-105B", site_id: "PLANT-GULF-01", severity: "high" },
    date: "2026-03-21",
  },
  {
    run_id: "RCA-2026-0395",
    status: "completed",
    event_id: "EVT-TURB-3310",
    title: "Gas Turbine Exhaust Temp Spread — GT-401",
    summary:
      "Exhaust temperature spread across combustion cans increased to 47°C (limit 55°C). Thermocouple TC-12 reads 28°C above average, suggesting fuel nozzle fouling on Can #3.",
    confidence: 0.76,
    hypothesis: [
      "Fuel nozzle fouling on combustion can #3",
      "Thermocouple TC-12 calibration drift",
      "Combustion liner cracking causing hot-spot",
    ],
    immediate_actions: [
      "Cross-check TC-12 with redundant thermocouple",
      "Schedule borescope inspection within 7 days",
      "Reduce load to 85% until inspection complete",
    ],
    pm_suggestions: [
      "Add fuel nozzle cleaning to next hot-gas-path inspection",
      "Recalibrate all exhaust thermocouples during next outage",
    ],
    context_meta: { asset_id: "GT-401", site_id: "PLANT-GULF-01", severity: "high" },
    date: "2026-03-20",
  },
  {
    run_id: "RCA-2026-0387",
    status: "completed",
    event_id: "EVT-HX-1104",
    title: "Heat Exchanger Fouling — HX-310A",
    summary:
      "Approach temperature increased 12°C over 30 days. Fouling factor calculation indicates tube-side deposit buildup. Chemical cleaning recommended before efficiency drops below 80%.",
    confidence: 0.91,
    hypothesis: [
      "Calcium carbonate scaling on tube-side surfaces",
      "Biological fouling from cooling water source",
    ],
    immediate_actions: [
      "Switch to standby exchanger HX-310B",
      "Schedule chemical cleaning within 5 days",
    ],
    pm_suggestions: [
      "Increase cooling water treatment dosage by 15%",
      "Install online fouling monitor for early detection",
      "Review water chemistry sampling frequency",
    ],
    context_meta: { asset_id: "HX-310A", site_id: "PLANT-GULF-01", severity: "medium" },
    date: "2026-03-19",
  },
  {
    run_id: "RCA-2026-0381",
    status: "completed",
    event_id: "EVT-MOT-2208",
    title: "Motor Winding Temperature Rise — MOT-150",
    summary:
      "Stator winding temperature trending 8°C above normal. Current imbalance of 4.2% detected across phases. Insulation resistance test shows gradual degradation over 6 months.",
    confidence: 0.72,
    hypothesis: [
      "Phase-to-phase insulation degradation in stator winding",
      "Voltage supply imbalance from upstream VFD",
      "Cooling fan airflow restriction from debris buildup",
    ],
    immediate_actions: [
      "Perform megger test on next available shutdown",
      "Check VFD output voltage balance",
      "Inspect and clean cooling fan inlet",
    ],
    pm_suggestions: [
      "Plan motor rewind during next turnaround window",
      "Add quarterly insulation resistance trending",
    ],
    context_meta: { asset_id: "MOT-150", site_id: "PLANT-GULF-01", severity: "medium" },
    date: "2026-03-18",
  },
  {
    run_id: "RCA-2026-0374",
    status: "completed",
    event_id: "EVT-VLV-4412",
    title: "Control Valve Stiction — CV-2240",
    summary:
      "Control valve CV-2240 exhibiting 3.8% dead-band with stick-slip behavior. Process variable oscillation causing ±2.1% flow deviation. Valve positioner recalibration required.",
    confidence: 0.88,
    hypothesis: [
      "Packing gland over-torqued causing excessive stem friction",
      "Valve plug and seat erosion from cavitation",
    ],
    immediate_actions: [
      "Adjust packing gland torque to specification",
      "Recalibrate Fisher DVC6200 positioner",
    ],
    pm_suggestions: [
      "Replace valve trim during next outage",
      "Install anti-cavitation trim if ΔP exceeds 150 psi",
      "Add valve signature test to quarterly PM routine",
    ],
    context_meta: { asset_id: "CV-2240", site_id: "PLANT-GULF-01", severity: "low" },
    date: "2026-03-17",
  },
  {
    run_id: "RCA-2026-0369",
    status: "completed",
    event_id: "EVT-GEN-6601",
    title: "Generator Bearing Oil Temp — GEN-501",
    summary:
      "Bearing #2 oil outlet temperature increased 6°C over 14 days. Oil particle count shows elevated ISO 18/15/12. Cooler effectiveness check and oil flush recommended.",
    confidence: 0.81,
    hypothesis: [
      "Lube oil cooler tube fouling reducing heat rejection",
      "Oil degradation from oxidation at elevated operating temps",
      "Bearing clearance wear increasing friction losses",
    ],
    immediate_actions: [
      "Flush lube oil system with clean charge",
      "Check oil cooler inlet/outlet temps for effectiveness",
    ],
    pm_suggestions: [
      "Replace lube oil charge — current oil has 14,200 operating hours",
      "Schedule bearing clearance measurement at next outage",
    ],
    context_meta: { asset_id: "GEN-501", site_id: "PLANT-GULF-01", severity: "medium" },
    date: "2026-03-16",
  },
  {
    run_id: "RCA-2026-0362",
    status: "completed",
    event_id: "EVT-COMP-5215",
    title: "Compressor Discharge Pressure Anomaly — COMP-340",
    summary:
      "Discharge pressure dropped 4.2% while suction conditions remained stable. Polytropic efficiency decreased from 82% to 77%. Anti-surge valve position indicates proximity to surge line.",
    confidence: 0.93,
    hypothesis: [
      "Impeller fouling reducing compression efficiency",
      "Labyrinth seal wear causing internal recirculation",
    ],
    immediate_actions: [
      "Increase anti-surge margin to 15%",
      "Monitor approach to surge line every 30 minutes",
      "Prepare for controlled shutdown if efficiency drops below 75%",
    ],
    pm_suggestions: [
      "Schedule impeller cleaning during next opportunity",
      "Inspect labyrinth seals and measure clearances",
    ],
    context_meta: { asset_id: "COMP-340", site_id: "PLANT-GULF-01", severity: "critical" },
    date: "2026-03-15",
  },
  {
    run_id: "RCA-2026-0355",
    status: "completed",
    event_id: "EVT-PIPE-8801",
    title: "Pipeline Corrosion Under Insulation — PL-6200",
    summary:
      "UT thickness measurement shows 18% wall loss at elbow section. Corrosion rate estimated at 0.8 mm/yr, exceeding the 0.3 mm/yr design allowance. Insulation replacement and recoating needed.",
    confidence: 0.86,
    hypothesis: [
      "Moisture ingress through damaged insulation jacketing",
      "Chloride stress corrosion from marine environment exposure",
    ],
    immediate_actions: [
      "Install temporary clamp if wall thickness below minimum",
      "Expand UT inspection to adjacent pipe sections",
    ],
    pm_suggestions: [
      "Replace insulation and apply epoxy coating system",
      "Add CUI inspection points to risk-based inspection program",
      "Consider upgrading insulation to closed-cell type",
    ],
    context_meta: { asset_id: "PL-6200", site_id: "PLANT-GULF-01", severity: "high" },
    date: "2026-03-14",
  },
  {
    run_id: "RCA-2026-0348",
    status: "completed",
    event_id: "EVT-INS-9902",
    title: "Pressure Transmitter Drift — PT-4410",
    summary:
      "Pressure transmitter PT-4410 drifting +1.8% from reference over 90 days. SIS loop test showed deviation within acceptable range but trending toward trip setpoint.",
    confidence: 0.69,
    hypothesis: [
      "Sensor diaphragm fatigue from pressure cycling",
      "Electronics drift from ambient temperature variation",
    ],
    immediate_actions: [
      "Perform field calibration check against reference gauge",
      "Document drift trend for SIL verification record",
    ],
    pm_suggestions: [
      "Replace transmitter during next SIS proof test interval",
      "Add redundant transmitter for 2oo3 voting architecture",
    ],
    context_meta: { asset_id: "PT-4410", site_id: "PLANT-GULF-01", severity: "low" },
    date: "2026-03-13",
  },
];

function mapRun(raw: RawRun): RcaRun {
  return {
    id: raw.run_id,
    asset_id: raw.context_meta?.asset_id ?? raw.run_id,
    severity: raw.context_meta?.severity ?? "unknown",
    summary: raw.summary || raw.title || "No summary available",
    confidence_score: raw.confidence ?? 0,
    created_at: raw.date ?? new Date().toISOString(),
    status: raw.status ?? "unknown",
    findings: raw.hypothesis,
    recommendations: raw.immediate_actions,
    pm_suggestions: raw.pm_suggestions,
    model_info: raw.model,
    context_metadata: raw.context_meta,
    title: raw.title,
  };
}

function buildHierarchyFromRuns(runs: RcaRun[]): HierarchyNode[] {
  const compressors = runs.filter((r) => r.asset_id.startsWith("COMP"));
  const pumps = runs.filter((r) => r.asset_id.startsWith("PS"));
  const turbines = runs.filter((r) => r.asset_id.startsWith("GT"));
  const exchangers = runs.filter((r) => r.asset_id.startsWith("HX"));
  const electrical = runs.filter((r) => r.asset_id.startsWith("MOT") || r.asset_id.startsWith("GEN"));
  const valves = runs.filter((r) => r.asset_id.startsWith("CV"));
  const piping = runs.filter((r) => r.asset_id.startsWith("PL"));
  const instruments = runs.filter((r) => r.asset_id.startsWith("PT"));

  const makeChildren = (items: RcaRun[]) =>
    items.map((r) => ({ id: r.asset_id, name: r.asset_id, type: "Equipment" }));

  const systems: HierarchyNode[] = [];
  if (compressors.length) systems.push({ id: "SYS-COMP", name: "Compression", type: "System", children: makeChildren(compressors) });
  if (pumps.length) systems.push({ id: "SYS-PUMP", name: "Pumping", type: "System", children: makeChildren(pumps) });
  if (turbines.length) systems.push({ id: "SYS-TURB", name: "Power Generation", type: "System", children: makeChildren(turbines) });
  if (exchangers.length) systems.push({ id: "SYS-HX", name: "Heat Exchange", type: "System", children: makeChildren(exchangers) });
  if (electrical.length) systems.push({ id: "SYS-ELEC", name: "Electrical Rotating", type: "System", children: makeChildren(electrical) });
  if (valves.length) systems.push({ id: "SYS-VLV", name: "Control Valves", type: "System", children: makeChildren(valves) });
  if (piping.length) systems.push({ id: "SYS-PIPE", name: "Piping & Structural", type: "System", children: makeChildren(piping) });
  if (instruments.length) systems.push({ id: "SYS-INS", name: "Instrumentation", type: "System", children: makeChildren(instruments) });

  return [
    {
      id: "PLANT-GULF-01",
      name: "Gulf Coast Processing Plant",
      type: "Site",
      children: [
        {
          id: "FAC-PROC",
          name: "Processing Facility",
          type: "Facility",
          children: systems,
        },
      ],
    },
  ];
}

function buildFailureEventsFromRuns(runs: RcaRun[]): FailureEvent[] {
  const downtimeMap: Record<string, number> = { critical: 18, high: 11, medium: 6, low: 2 };
  return runs.map((run) => ({
    id: String(run.id),
    asset_id: String(run.asset_id),
    failure_mode: run.title || run.summary || "Potential equipment degradation",
    severity: run.severity || "medium",
    downtime_hours: downtimeMap[run.severity?.toLowerCase() || "medium"] || 6,
    date: run.created_at || new Date().toISOString(),
  }));
}

export const api = {
  getRuns: async () => {
    try {
      const raw = await apiFetch<RawRun[]>("/api/v1/portal/runs");
      if (!Array.isArray(raw) || raw.length === 0) {
        return FALLBACK_RUNS.map(mapRun);
      }
      return raw.map(mapRun);
    } catch {
      return FALLBACK_RUNS.map(mapRun);
    }
  },

  getRunDetail: async (id: string) => {
    try {
      const raw = await apiFetch<RawRun>(`/api/v1/portal/runs/${id}`);
      return mapRun(raw);
    } catch {
      const runs = await api.getRuns();
      const match = runs.find((run) => run.id === id);
      if (match) return match;
      throw new Error("Run not found");
    }
  },

  getHierarchy: async () => {
    try {
      const hierarchy = await apiFetch<HierarchyNode[]>("/api/v1/hierarchy");
      if (Array.isArray(hierarchy) && hierarchy.length > 0) {
        return hierarchy;
      }
      throw new Error("Hierarchy endpoint returned no data");
    } catch {
      const runs = await api.getRuns();
      return buildHierarchyFromRuns(runs);
    }
  },

  getFailureEvents: async () => {
    try {
      const events = await apiFetch<FailureEvent[]>("/api/v1/failure-events");
      if (Array.isArray(events) && events.length > 0) {
        return events;
      }
      throw new Error("Failure events endpoint returned no data");
    } catch {
      const runs = await api.getRuns();
      return buildFailureEventsFromRuns(runs);
    }
  },
  getHealthDeep: async () => apiFetch<any>("/healthz?deep=true"),
  getOutcomes: async (window = 30) => apiFetch<any>(`/api/v1/reports/rca-outcomes?window=${window}`),
  getBadActors: async (limit = 5) => apiFetch<any[]>(`/api/v1/reports/bad-actors?limit=${limit}`),
  getSignalsSummary: async (assetId: string) => apiFetch<any>(`/api/v1/signals/summary?asset_id=${assetId}`),
  analyzePm: async (body: object) => apiFetch<any>("/api/v1/agents/pm/advisor/analyze", { method: "POST", body: JSON.stringify(body) }),
  approvePmProposal: async (id: string) => apiFetch<any>(`/api/v1/agents/pm/proposals/${id}/approve`, { method: "POST" }),
  submitFeedback: async (body: object) => apiFetch<any>("/api/v1/feedback", { method: "POST", body: JSON.stringify(body) }),
};

// Named exports for PmAdvisor compatibility
export async function getPmProposals(): Promise<any[]> {
  return apiFetch<any[]>("/api/v1/agents/pm/proposals");
}
export async function approvePmProposal(id: string): Promise<any> {
  return apiFetch<any>(`/api/v1/agents/pm/proposals/${id}/approve`, { method: "POST" });
}

// Named exports for Outcomes page compatibility
export async function getRcaOutcomes(window = 30): Promise<any> {
  return apiFetch<any>(`/api/v1/reports/rca-outcomes?window=${window}`);
}
export async function getBadActors(limit = 20): Promise<any[]> {
  return apiFetch<any[]>(`/api/v1/reports/bad-actors?limit=${limit}`);
}
export type BadActor = any;
export type RcaOutcomeSummary = any;

// Named export for RunDetail feedback
export async function submitFeedback(body: { run_id: string; action: string }): Promise<any> {
  return apiFetch<any>("/api/v1/feedback", { method: "POST", body: JSON.stringify(body) });
}

// Named exports for RunDetail compatibility
export async function getPortalRuns(): Promise<any[]> {
  return apiFetch<any[]>("/api/v1/portal/runs");
}

// Remaining named exports for page compatibility
export async function getRunDetail(id: string): Promise<any> {
  return apiFetch<any>(`/api/v1/portal/runs/${id}`);
}
export async function getSystemHealth(): Promise<any> {
  return apiFetch<any>("/healthz?deep=true");
}
export type HealthPayload = any;
export type PmProposal = any;
export type HierarchyNode = {
  id: string;
  name: string;
  type: string;
  children?: HierarchyNode[];
};
