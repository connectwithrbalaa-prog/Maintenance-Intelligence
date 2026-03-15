from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_REPO = "connectwithrbalaa-prog/Maintenance-Intelligence"


def _run_gh_json(args: list[str]) -> Any:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gh command failed")
    return json.loads(result.stdout)


def _load_json(path: str | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_compare_data(repo: str, since_tag: str, to_tag: str, compare_data_file: str | None) -> dict[str, Any]:
    fixture = _load_json(compare_data_file)
    if fixture is not None:
        return fixture
    return _run_gh_json(["gh", "api", f"repos/{repo}/compare/{since_tag}...{to_tag}"])


def fetch_commit_pr_map(
    repo: str,
    commit_shas: list[str],
    commit_pr_map_file: str | None,
) -> dict[str, list[dict[str, Any]]]:
    fixture = _load_json(commit_pr_map_file)
    if fixture is not None:
        return fixture

    commit_pr_map: dict[str, list[dict[str, Any]]] = {}
    for sha in commit_shas:
        commit_pr_map[sha] = _run_gh_json(
            [
                "gh",
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repo}/commits/{sha}/pulls",
            ]
        )
    return commit_pr_map


def collect_changes(
    compare_data: dict[str, Any],
    commit_pr_map: dict[str, list[dict[str, Any]]],
) -> list[str]:
    changes: list[str] = []
    seen_prs: set[int] = set()

    for commit in compare_data.get("commits", []):
        sha = commit.get("sha", "")
        pull_requests = sorted(
            commit_pr_map.get(sha, []),
            key=lambda item: (item.get("mergedAt") or "", item.get("number") or 0),
        )
        added_pr = False
        for pull_request in pull_requests:
            number = pull_request.get("number")
            title = (pull_request.get("title") or "").strip()
            if not isinstance(number, int) or not title or number in seen_prs:
                continue
            seen_prs.add(number)
            changes.append(f"- {title} (#{number})")
            added_pr = True

        if added_pr:
            continue

        summary = ((commit.get("commit") or {}).get("message") or "").splitlines()[0].strip()
        if summary:
            short_sha = sha[:7] if sha else "unknown"
            changes.append(f"- {summary} (commit {short_sha})")

    return changes


def collect_contributors(compare_data: dict[str, Any]) -> list[str]:
    contributors: set[str] = set()
    for commit in compare_data.get("commits", []):
        author = commit.get("author") or {}
        login = author.get("login")
        if login:
            contributors.add(f"@{login}")
            continue

        fallback_name = ((commit.get("commit") or {}).get("author") or {}).get("name")
        if fallback_name:
            contributors.add(str(fallback_name))

    return sorted(contributors, key=str.casefold)


def format_release_notes(to_tag: str, changes: list[str], contributors: list[str]) -> str:
    lines = [
        f"# Maintenance Intelligence {to_tag}",
        "",
        "## Changes",
        "",
    ]
    lines.extend(changes or ["- No changes found"])
    lines.extend(["", "## Contributors", ""])
    lines.extend([f"- {contributor}" for contributor in contributors] or ["- No contributors found"])
    lines.append("")
    return "\n".join(lines)


def build_release_notes(
    repo: str,
    since_tag: str,
    to_tag: str,
    compare_data_file: str | None = None,
    commit_pr_map_file: str | None = None,
) -> str:
    compare_data = fetch_compare_data(repo, since_tag, to_tag, compare_data_file)
    commit_shas = [commit.get("sha") for commit in compare_data.get("commits", []) if commit.get("sha")]
    commit_pr_map = fetch_commit_pr_map(repo, commit_shas, commit_pr_map_file)
    changes = collect_changes(compare_data, commit_pr_map)
    contributors = collect_contributors(compare_data)
    return format_release_notes(to_tag, changes, contributors)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate release notes from a GitHub compare range")
    parser.add_argument("since_tag", nargs="?", default="v0.1.0")
    parser.add_argument("to_tag", nargs="?", default="v0.2.0")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--compare-data-file")
    parser.add_argument("--commit-pr-map-file")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    release_notes = build_release_notes(
        repo=args.repo,
        since_tag=args.since_tag,
        to_tag=args.to_tag,
        compare_data_file=args.compare_data_file,
        commit_pr_map_file=args.commit_pr_map_file,
    )
    if args.output:
        Path(args.output).write_text(release_notes, encoding="utf-8")
    else:
        print(release_notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())