set -euo pipefail
REPO="connectwithrbalaa-prog/Maintenance-Intelligence"
MILESTONE_TITLE="v0.2.0"
MILESTONE_DESC="RCA structure + signals + RAG enhancements + DB/ops hardening + observability + dashboards + DX"
gh api repos/$REPO/milestones -X POST -f title="$MILESTONE_TITLE" -f state=open -f description="$MILESTONE_DESC" >/dev/null || true
MS_NUMBER=$(gh api repos/$REPO/milestones | jq -r '.[] | select(.title=="'"$MILESTONE_TITLE"'") | .number')
create_issue() { gh issue create --repo "$REPO" --title "$1" --body "$2" --milestone "$MILESTONE_TITLE" --label "enhancement"; }
create_issue "RCA: Structured rationale/evidence + confidence per section" "Refactor the RCA prompt and output to structured JSON fields (title, rationale bullets, evidence references, confidence per section). Persist evidence IDs (signals/doc chunks) and confidence."
create_issue "RCA: Model switcher and routing policy" "Config-based routing for assets/event classes (e.g., gpt-4.1 vs gpt-5), with cost/latency trade-offs. Add unit tests for policy selection."
create_issue "Signals: Real rollups and anomaly flags" "Produce rolling means/min/max over 1h/6h/24h windows from measurements. Flag anomalies/threshold breaches to feed RCA evidence."
create_issue "RAG: pgvector index + hybrid retrieval" "Enable ivfflat index, tune lists, add hybrid retrieval (BM25 + vector). Add context budgeter to pack top chunks within token budget."
create_issue "DB/Ops: Alembic migrations + graceful Kafka shutdown + retries" "Move to Alembic versioned migrations. Add consumer backpressure/retry strategy and graceful shutdown hooks."
create_issue "Observability: OTel hooks + run digest + correlation" "Add optional OpenTelemetry traces/metrics; produce compact run digests; align structured logging for run_id across services."
create_issue "Dashboards: Bad Actor v2 + RCA outcomes" "Add trends/MTBF/MTTR approximations; outcomes report (acceptance rate, time-to-WO)."
create_issue "Health: Deeper deep-checks (topics, lag estimates)" "Extend /healthz?deep=true to validate topic existence and produce coarse lag estimates."
create_issue "DX/Tooling: Make targets, compose stack, CI matrix + coverage gate" "Add make targets for compose-based dev stack, CI 3.10/3.11, and coverage threshold."
echo "Milestone and issues created. Milestone #$MS_NUMBER"