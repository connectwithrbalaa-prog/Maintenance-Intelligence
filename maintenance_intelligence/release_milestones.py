from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_REPO = "connectwithrbalaa-prog/Maintenance-Intelligence"
DEFAULT_MILESTONE_TITLE = "v0.3.0"
DEFAULT_MILESTONE_DESCRIPTION = (
    "Model routing + feedback loop + outcomes analytics + SLO/autoscaling + "
    "multi-tenant security + context governance"
)
DEFAULT_ISSUES = [
    {
        "title": "Model routing and cost controls",
        "body": (
            "Route RCA by asset/event class (gpt-4.1 vs gpt-5); per-model budgets and "
            "circuit breakers; metrics for model spend and rejection."
        ),
    },
    {
        "title": "RCA feedback loop",
        "body": (
            "Capture operator accept/reject/edits; store learned corrections and reasons; "
            "feed into prompt tuning/heuristics."
        ),
    },
    {
        "title": "Outcomes analytics (TTR, MTBF/MTTR, acceptance rate)",
        "body": "Add panels + CSV exports; correlate RCA recommendations with WO outcomes/time-to-resolution.",
    },
    {
        "title": "SLO tuning and autoscaling hooks",
        "body": "Tune thresholds; expose queue depth/parallelism; add hooks for HPA signals (if k8s) or process scaling guidance.",
    },
    {
        "title": "Multi-tenant and security hardening",
        "body": "Org/site isolation (topics + DB); audit logs; role-based RCA trigger/override; secret scanning and config checks.",
    },
    {
        "title": "Context governance and PII scrubbing",
        "body": "Sanitize run summaries; provenance scoring for chunks; token budget enforcement and redaction.",
    },
    {
        "title": "Prompt catalog and A/B testing",
        "body": "Manage prompt variants; A/B evaluate RCA quality; automated canary with rollback if quality drops.",
    },
    {
        "title": "Operator UX: feedback endpoints + UI stubs",
        "body": "API for feedback submission; minimal UI mock or docs; link feedback to runs in summaries.",
    },
    {
        "title": "GenAI cost/latency dashboards",
        "body": "Grafana panels for cost per run, latency per model; weekly budget rollups and alerts.",
    },
]


def _load_records(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None

    file_path = Path(path)
    if file_path.suffix.lower() == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON list in {path}")
        return data

    if file_path.suffix.lower() == ".csv":
        with file_path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    raise ValueError(f"Unsupported fixture format for {path}")


def _normalize_issue_definitions(records: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    source = records if records is not None else DEFAULT_ISSUES
    issues: list[dict[str, str]] = []
    for record in source:
        title = str(record.get("title", "")).strip()
        body = str(record.get("body", "")).strip()
        label = str(record.get("label", "enhancement")).strip() or "enhancement"
        if not title or not body:
            raise ValueError(f"Invalid issue definition: {record}")
        issues.append({"title": title, "body": body, "label": label})
    return issues


class GitHubCLI:
    def __init__(self, dry_run: bool = False, max_attempts: int = 3, backoff_seconds: float = 1.0):
        self.dry_run = dry_run
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        last_result: subprocess.CompletedProcess[str] | None = None
        for attempt in range(1, self.max_attempts + 1):
            result = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            last_result = result
            if result.returncode == 0:
                return result
            if attempt < self.max_attempts:
                time.sleep(self.backoff_seconds * attempt)

        assert last_result is not None
        raise RuntimeError(last_result.stderr.strip() or last_result.stdout.strip() or "gh command failed")

    def ensure_milestone(self, repo: str, title: str, description: str) -> None:
        args = [
            "gh",
            "api",
            f"repos/{repo}/milestones",
            "-X",
            "POST",
            "-f",
            f"title={title}",
            "-f",
            "state=open",
            "-f",
            f"description={description}",
        ]
        if self.dry_run:
            print("DRY-RUN:", " ".join(args))
            return
        try:
            self._run(args)
        except RuntimeError as error:
            message = str(error).casefold()
            if "already_exists" in message or "already exists" in message or "validation failed" in message:
                return
            raise

    def create_issue(self, repo: str, milestone_title: str, issue: dict[str, str]) -> None:
        args = [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            issue["title"],
            "--body",
            issue["body"],
            "--milestone",
            milestone_title,
            "--label",
            issue["label"],
        ]
        if self.dry_run:
            print("DRY-RUN:", " ".join(args))
            return
        self._run(args)


def seed_milestone(
    repo: str = DEFAULT_REPO,
    milestone_title: str = DEFAULT_MILESTONE_TITLE,
    milestone_description: str = DEFAULT_MILESTONE_DESCRIPTION,
    issue_data_file: str | None = None,
    dry_run: bool = False,
    gh: GitHubCLI | None = None,
) -> dict[str, Any]:
    github = gh or GitHubCLI(dry_run=dry_run)
    issues = _normalize_issue_definitions(_load_records(issue_data_file))
    if not issues:
        raise ValueError("No issue definitions found")

    github.ensure_milestone(repo, milestone_title, milestone_description)
    for issue in issues:
        github.create_issue(repo, milestone_title, issue)

    return {
        "repo": repo,
        "milestone_title": milestone_title,
        "issue_count": len(issues),
        "titles": [issue["title"] for issue in issues],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a GitHub milestone and its issues safely")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--milestone-title", default=DEFAULT_MILESTONE_TITLE)
    parser.add_argument("--milestone-description", default=DEFAULT_MILESTONE_DESCRIPTION)
    parser.add_argument("--issue-data-file")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = seed_milestone(
        repo=args.repo,
        milestone_title=args.milestone_title,
        milestone_description=args.milestone_description,
        issue_data_file=args.issue_data_file,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "repo": result["repo"],
                "milestone_title": result["milestone_title"],
                "issue_count": result["issue_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())