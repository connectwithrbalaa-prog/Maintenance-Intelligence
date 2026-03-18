# Stack Review Checklist

Use this checklist when reviewing the stacked PR plan for `feature/rca-structured-output`.

## PR 1: Foundation Workflows

- Confirm runner/service orchestration boundaries are clear.
- Confirm GenAI gateway contracts remain compatible with RCA callers.
- Confirm context assembly fallback behavior is deterministic under missing tables or partial data.
- Confirm migrations are forward-safe and smoke coverage matches expected schema.
- Confirm PM approval baseline behavior remains idempotent.
- Confirm outcomes persistence uses the intended timestamp columns.

### Validation

- RCA structured output tests pass.
- RCA stub and integration tests pass.
- Health and migration smoke tests pass.
- PM approval and retry tests pass.
- Outcomes API, import, and mock smoke tests pass.

### Risk Focus

- Schema drift.
- RCA contract breakage.
- PM retry semantics.

## PR 2: Handoff Queue UX

- Confirm portal queue views reflect actual backend queue states.
- Confirm sorting, filtering, and summary chips are internally consistent.
- Confirm empty-state variants match connector-failure and no-data cases.
- Confirm per-user queue preferences persist and restore correctly.
- Confirm PM follow-through snapshot data matches proposal response payloads.

### Validation

- Portal queue view tests pass.
- PM proposal API tests still pass with enriched responses.
- Connector-failure scenarios render expected UI state.
- Retry counters and SLA-aging displays line up with payload values.

### Risk Focus

- UI state drift from API semantics.
- Preference persistence regressions.
- Queue summary chips misreporting counts or ages.

## PR 3: RCA and Triage Intelligence

- Confirm structured repair-plan persistence preserves existing RCA read and write contracts.
- Confirm evidence references and drift views point to the correct source records.
- Confirm prioritized asset scoring produces stable ordering.
- Confirm triage drill-through and deep-link paths land in the correct evidence context.
- Confirm fleet-wide context inclusion does not pollute local-only results unexpectedly.
- Confirm PdM early-warning ordering and warnings-only filtering behave as designed.

### Validation

- Repair plan persistence tests pass.
- Prioritized asset report tests pass.
- Portal triage tests pass.
- RCA evidence context tests pass.
- Retrieval and scoring tests pass.
- PdM and outcomes tests pass.

### Risk Focus

- Ranking logic regressions.
- Cross-asset context leakage.
- Evidence-to-portal linking errors.

## PR 4: Edge Resilience

- Confirm event buffering and replay remains opt-in and only active in edge mode.
- Confirm command buffering and replay is idempotent across retries.
- Confirm portal, metrics, and deep health expose consistent edge state.
- Confirm local RCA fallback activates only in degraded edge scenarios.
- Confirm replay failure counters and timestamps are updated correctly.

### Validation

- Edge buffer tests pass.
- Edge command buffer tests pass.
- WO bridge replay tests pass.
- Metrics endpoint tests pass.
- Deep health tests pass.
- RCA local fallback tests pass.

### Risk Focus

- Duplicate replays.
- Incorrect degraded-mode activation.
- Mismatched diagnostics across API surfaces.

## Cross-PR Merge Gate

- `git status` is clean before each PR branch is pushed.
- `git diff --check` is clean against the PR base branch.
- No unresolved migration ordering issues remain.
- Each PR body explicitly states scope and non-goals.
- Reviewer notes call out stack dependencies and review order.