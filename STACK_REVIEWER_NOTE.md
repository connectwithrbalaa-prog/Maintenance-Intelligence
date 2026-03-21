# Reviewer Note

This work is split as a stack because the original branch grew too large to review safely as one PR.

## Stack Order

1. `stack/foundation-workflows`
2. `stack/handoff-queue-ux`
3. `stack/rca-triage-intelligence`
4. `stack/edge-resilience`

## Why This Order

- PR 1 establishes the runtime, RCA, PM, outcomes, migration, and test foundation.
- PR 2 layers the operator-facing handoff queue workflow on top of that baseline.
- PR 3 adds the RCA evidence, scoring, context, and triage intelligence changes.
- PR 4 isolates edge and offline resilience behavior so degraded-mode logic is reviewed separately.

## Recommended Review Approach

- Review each PR against its immediate base branch rather than against `main`.
- Focus first on behavior contracts and persistence semantics.
- Treat BRD completeness as a scope question, not as line-by-line review criteria for these PRs.

## Reviewer Focus by PR

### PR 1: Foundation Workflows

- RCA and GenAI integration contracts
- migration safety and schema assumptions
- PM retry and idempotency behavior
- outcomes persistence and smoke coverage

### PR 2: Handoff Queue UX

- queue state semantics
- failure and empty-state handling
- preference persistence behavior
- PM and operator workflow coherence

### PR 3: RCA and Triage Intelligence

- scoring and ranking behavior
- RCA evidence and repair-plan contract stability
- fleet-context retrieval scope
- warnings-only and PdM ordering semantics

### PR 4: Edge Resilience

- replay idempotency and failure tracking
- portal, metrics, and health diagnostic consistency
- fallback activation conditions
- edge-mode behavior under connector or GenAI outage

## Known Follow-up Gaps Still Out of Scope

- production auth and tenant isolation
- broader connector coverage
- governed or pre-cached context infrastructure
- notification routing
- full BRD completion