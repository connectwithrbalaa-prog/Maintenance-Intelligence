#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${REMOTE:-origin}"
REPO="${REPO:-connectwithrbalaa-prog/Maintenance-Intelligence}"
BASE_BRANCH="${BASE_BRANCH:-main}"
PUSH_BRANCHES="${PUSH_BRANCHES:-0}"
CREATE_PRS="${CREATE_PRS:-0}"
FORCE_BRANCH_RESET="${FORCE_BRANCH_RESET:-0}"

FOUNDATION_REF="${FOUNDATION_REF:-59340f3}"
HANDOFF_REF="${HANDOFF_REF:-bc9bd59}"
TRIAGE_REF="${TRIAGE_REF:-b4e1516}"
EDGE_REF="${EDGE_REF:-7a74b8e}"

FOUNDATION_BRANCH="stack/foundation-workflows"
HANDOFF_BRANCH="stack/handoff-queue-ux"
TRIAGE_BRANCH="stack/rca-triage-intelligence"
EDGE_BRANCH="stack/edge-resilience"

require_clean_worktree() {
    if [[ -n "$(git status --short)" ]]; then
        echo "Working tree is not clean. Commit or stash changes before running this script." >&2
        exit 1
    fi
}

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Required command not found: $cmd" >&2
        exit 1
    fi
}

create_branch() {
    local branch="$1"
    local start_point="$2"

    if git show-ref --verify --quiet "refs/heads/$branch"; then
        if [[ "$FORCE_BRANCH_RESET" != "1" ]]; then
            echo "Local branch '$branch' already exists. Re-run with FORCE_BRANCH_RESET=1 to recreate it." >&2
            exit 1
        fi
        git branch -D "$branch"
    fi

    git switch -c "$branch" "$start_point"
}

verify_ancestry_chain() {
    local foundation_base
    local handoff_base
    local triage_base
    local edge_base

    foundation_base="$(git merge-base "$REMOTE/$BASE_BRANCH" "$FOUNDATION_REF")"
    handoff_base="$(git merge-base "$FOUNDATION_REF" "$HANDOFF_REF")"
    triage_base="$(git merge-base "$HANDOFF_REF" "$TRIAGE_REF")"
    edge_base="$(git merge-base "$TRIAGE_REF" "$EDGE_REF")"

    if [[ "$foundation_base" != "$(git rev-parse "$REMOTE/$BASE_BRANCH")" ]]; then
        echo "Foundation ref '$FOUNDATION_REF' is not based on $REMOTE/$BASE_BRANCH as expected." >&2
        exit 1
    fi

    if [[ "$handoff_base" != "$(git rev-parse "$FOUNDATION_REF")" ]]; then
        echo "Handoff ref '$HANDOFF_REF' does not descend from foundation ref '$FOUNDATION_REF'." >&2
        exit 1
    fi

    if [[ "$triage_base" != "$(git rev-parse "$HANDOFF_REF")" ]]; then
        echo "Triage ref '$TRIAGE_REF' does not descend from handoff ref '$HANDOFF_REF'." >&2
        exit 1
    fi

    if [[ "$edge_base" != "$(git rev-parse "$TRIAGE_REF")" ]]; then
        echo "Edge ref '$EDGE_REF' does not descend from triage ref '$TRIAGE_REF'." >&2
        exit 1
    fi
}

maybe_push_branch() {
    local branch="$1"
    if [[ "$PUSH_BRANCHES" == "1" ]]; then
        git push -u "$REMOTE" "$branch"
    fi
}

write_body_file() {
    local path="$1"
    local content="$2"
    printf '%s\n' "$content" >"$path"
}

maybe_create_pr() {
    local base="$1"
    local head="$2"
    local title="$3"
    local body_file="$4"

    if [[ "$CREATE_PRS" != "1" ]]; then
        return
    fi

    require_command gh
    gh pr create \
        --repo "$REPO" \
        --base "$base" \
        --head "$head" \
        --title "$title" \
        --body-file "$body_file"
}

main() {
    require_command git

    cd "$ROOT_DIR"
    require_clean_worktree
    git fetch "$REMOTE"
    verify_ancestry_chain

    create_branch "$FOUNDATION_BRANCH" "$FOUNDATION_REF"
    maybe_push_branch "$FOUNDATION_BRANCH"
    foundation_body="$(mktemp)"
    write_body_file "$foundation_body" "## Summary
Establishes the branch foundation for RCA, PM, outcomes, migrations, and service/runtime plumbing.

## Included
- runner/service orchestration and CLI/API bootstrap
- GenAI gateway integration for RCA and run summaries
- MVP context assembly and RAG bootstrap
- SQL-first migrations and deep health checks
- PM approval baseline hardening, retries, audit history, and portal identity/demo support
- outcomes metrics and lifecycle timestamp persistence
- portal smoke harness, CI, and migration smoke coverage
- schema alignment and outcomes mock smoke

## Reviewer focus
- RCA and GenAI integration contracts
- migration safety and schema assumptions
- PM retry/idempotency behavior
- outcomes persistence and smoke coverage"
    maybe_create_pr "$BASE_BRANCH" "$FOUNDATION_BRANCH" "feat: establish RCA, PM, outcomes, and migration foundations" "$foundation_body"

    create_branch "$HANDOFF_BRANCH" "$HANDOFF_REF"
    maybe_push_branch "$HANDOFF_BRANCH"
    handoff_body="$(mktemp)"
    write_body_file "$handoff_body" "## Summary
Adds PM follow-through and the portal handoff queue operator workflow on top of the foundation branch.

## Included
- PM follow-through snapshotting and richer proposal responses
- actionable handoff-exception queue controls
- queue views, sort controls, and per-user preferences
- SLA aging signals and retries-remaining surfacing
- connector-failure views and tailored empty states
- summary chips for lead age, aging risk, current rank, visible classes, longest wait, and active sort state

## Reviewer focus
- queue state semantics
- failure and empty-state handling
- preference persistence behavior
- PM/operator workflow coherence"
    maybe_create_pr "$FOUNDATION_BRANCH" "$HANDOFF_BRANCH" "feat(portal): add PM follow-through and handoff queue operator UX" "$handoff_body"

    create_branch "$TRIAGE_BRANCH" "$TRIAGE_REF"
    maybe_push_branch "$TRIAGE_BRANCH"
    triage_body="$(mktemp)"
    write_body_file "$triage_body" "## Summary
Adds structured repair-plan persistence, RCA evidence UX, prioritized asset scoring, fleet context, and PdM-driven triage behavior.

## Included
- secure RCA reads and persisted structured repair plans
- portal evidence context, evidence references, and drift comparisons
- prioritized asset risk scoring and triage wiring
- triage drill-through and evidence deep-links
- fleet-wide context assembly
- deterministic PdM early-warning scoring
- PdM-critical/elevated highlighting
- triage ordering and optional warnings-only filtering

## Reviewer focus
- scoring and ranking behavior
- RCA evidence and repair-plan contract stability
- fleet-context retrieval scope
- warnings-only and PdM ordering semantics"
    maybe_create_pr "$HANDOFF_BRANCH" "$TRIAGE_BRANCH" "feat: add RCA evidence, prioritized triage, and PdM early-warning intelligence" "$triage_body"

    create_branch "$EDGE_BRANCH" "$EDGE_REF"
    maybe_push_branch "$EDGE_BRANCH"
    edge_body="$(mktemp)"
    write_body_file "$edge_body" "## Summary
Adds edge-mode resilience through local ingestion buffering, CMMS command replay, diagnostics, and deterministic local RCA fallback.

## Included
- opt-in local event buffering and replay for ingestion
- command buffering and replay for CMMS handoff
- edge diagnostics in metrics, health, and portal status surfaces
- deterministic local RCA fallback when GenAI is unavailable in edge mode
- whitespace cleanup needed for branch diff hygiene

## Reviewer focus
- replay idempotency and failure tracking
- portal/metrics/health diagnostic consistency
- fallback activation conditions
- edge-mode behavior under connector or GenAI outage"
    maybe_create_pr "$TRIAGE_BRANCH" "$EDGE_BRANCH" "feat(edge): add buffering, replay, diagnostics, and local RCA fallback" "$edge_body"

    echo
    echo "Stack branches created successfully:"
    echo "  $FOUNDATION_BRANCH"
    echo "  $HANDOFF_BRANCH"
    echo "  $TRIAGE_BRANCH"
    echo "  $EDGE_BRANCH"
    echo
    if [[ "$PUSH_BRANCHES" == "1" ]]; then
        echo "Branches were pushed to $REMOTE."
    else
        echo "Branches were created locally only. Re-run with PUSH_BRANCHES=1 to push them."
    fi

    if [[ "$CREATE_PRS" == "1" ]]; then
        echo "Pull requests were created via gh."
    else
        echo "Pull requests were not created. Re-run with CREATE_PRS=1 after pushing branches."
    fi
}

main "$@"