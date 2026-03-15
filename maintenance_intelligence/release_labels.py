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
DEFAULT_LABELS = [
    {"name": "AI/ML", "color": "5319e7", "description": "AI models, prompts, routing, feedback"},
    {"name": "Observability", "color": "1f78b4", "description": "Metrics, tracing, dashboards"},
    {"name": "Security", "color": "e31a1c", "description": "RBAC, multi-tenant, PII, audit"},
    {"name": "Scalability", "color": "33a02c", "description": "SLOs, autoscaling, throughput"},
    {"name": "UX", "color": "ff7f00", "description": "Operator endpoints, UI, docs"},
]
TITLE_LABEL_RULES = [
    (["model routing"], ["AI/ML", "Scalability"]),
    (["feedback loop"], ["AI/ML", "UX"]),
    (["outcomes analytics"], ["Observability", "UX"]),
    (["slo tuning and autoscaling"], ["Scalability"]),
    (["multi-tenant", "security"], ["Security"]),
    (["context governance", "pii"], ["Security", "AI/ML"]),
    (["prompt catalog", "a/b"], ["AI/ML"]),
    (["operator ux", "feedback endpoints"], ["UX"]),
    (["cost/latency dashboards"], ["Observability"]),
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


def _normalize_label_records(records: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    source = records if records is not None else DEFAULT_LABELS
    labels: list[dict[str, str]] = []
    for record in source:
        name = str(record.get("name", "")).strip()
        color = str(record.get("color", "")).strip()
        description = str(record.get("description", "")).strip()
        if not name or not color or not description:
            raise ValueError(f"Invalid label definition: {record}")
        labels.append({"name": name, "color": color, "description": description})
    return labels


def _normalize_issue_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for record in records:
        raw_number = record.get("number")
        title = str(record.get("title", "")).strip()
        if raw_number in (None, "") or not title:
            raise ValueError(f"Invalid issue record: {record}")
        issues.append({"number": int(raw_number), "title": title})
    return issues


def labels_for_title(title: str) -> list[str]:
    normalized_title = title.casefold()
    labels: list[str] = []
    for patterns, mapped_labels in TITLE_LABEL_RULES:
        if any(pattern in normalized_title for pattern in patterns):
            for label in mapped_labels:
                if label not in labels:
                    labels.append(label)
    return labels


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

    def list_open_milestone_issues(self, repo: str, milestone_title: str) -> list[dict[str, Any]]:
        result = self._run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--milestone",
                milestone_title,
                "--state",
                "open",
                "--json",
                "number,title",
            ]
        )
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            raise RuntimeError("Unexpected gh issue list output")
        return data

    def ensure_label(self, repo: str, label: dict[str, str]) -> None:
        args = [
            "gh",
            "label",
            "create",
            label["name"],
            "--repo",
            repo,
            "--color",
            label["color"],
            "--description",
            label["description"],
        ]
        if self.dry_run:
            print("DRY-RUN:", " ".join(args))
            return
        try:
            self._run(args)
        except RuntimeError as error:
            message = str(error).casefold()
            if "already exists" in message or "name already exists" in message:
                return
            raise

    def add_labels(self, repo: str, issue_number: int, labels: list[str]) -> None:
        args = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
        for label in labels:
            args.extend(["--add-label", label])
        if self.dry_run:
            print("DRY-RUN:", " ".join(args))
            return
        self._run(args)


def seed_and_tag_issues(
    repo: str = DEFAULT_REPO,
    milestone_title: str = DEFAULT_MILESTONE_TITLE,
    issue_data_file: str | None = None,
    label_data_file: str | None = None,
    dry_run: bool = False,
    gh: GitHubCLI | None = None,
) -> dict[str, Any]:
    github = gh or GitHubCLI(dry_run=dry_run)
    labels = _normalize_label_records(_load_records(label_data_file))
    issue_records = _load_records(issue_data_file)
    if issue_records is None:
        issue_records = github.list_open_milestone_issues(repo, milestone_title)

    issues = _normalize_issue_records(issue_records)
    if not issues:
        raise ValueError(f"No open issues found for milestone {milestone_title}")

    for label in labels:
        github.ensure_label(repo, label)

    tagged_issues: list[dict[str, Any]] = []
    for issue in issues:
        matched_labels = labels_for_title(issue["title"])
        if not matched_labels:
            continue
        github.add_labels(repo, issue["number"], matched_labels)
        tagged_issues.append({**issue, "labels": matched_labels})

    return {
        "repo": repo,
        "milestone_title": milestone_title,
        "total_issues": len(issues),
        "tagged_issues": tagged_issues,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed labels and tag milestone issues safely")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--milestone-title", default=DEFAULT_MILESTONE_TITLE)
    parser.add_argument("--issue-data-file")
    parser.add_argument("--label-data-file")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = seed_and_tag_issues(
        repo=args.repo,
        milestone_title=args.milestone_title,
        issue_data_file=args.issue_data_file,
        label_data_file=args.label_data_file,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "repo": result["repo"],
                "milestone_title": result["milestone_title"],
                "total_issues": result["total_issues"],
                "tagged_issue_count": len(result["tagged_issues"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())