from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_REPO = "connectwithrbalaa-prog/Maintenance-Intelligence"
DEFAULT_V0_2_0_PULL_REQUESTS = [19, 20, 21, 22, 23, 24, 25]


def _normalize_record(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    return {"number": record}


def _load_records(path: str | None) -> list[Any] | None:
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


def _normalize_pull_request_numbers(
    pull_request_numbers: list[int] | None = None,
    records: list[Any] | None = None,
) -> list[int]:
    source: list[Any]
    if records is not None:
        source = records
    elif pull_request_numbers:
        source = pull_request_numbers
    else:
        source = DEFAULT_V0_2_0_PULL_REQUESTS

    numbers: list[int] = []
    for record in source:
        raw_number = record.get("number") if isinstance(record, dict) else record
        if raw_number in (None, ""):
            raise ValueError(f"Invalid pull request record: {record}")
        try:
            number = int(raw_number)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid pull request record: {record}") from error
        numbers.append(number)

    if not numbers:
        raise ValueError("No pull request numbers found")

    return numbers


def _match_pull_request_record(
    record: dict[str, Any],
    state: str | None = None,
    base: str | None = None,
    head: str | None = None,
    author: str | None = None,
    labels: list[str] | None = None,
    search: str | None = None,
) -> bool:
    normalized_state = str(record.get("state", "")).strip().casefold()
    normalized_base = str(record.get("base", record.get("baseRefName", ""))).strip().casefold()
    normalized_head = str(record.get("head", record.get("headRefName", ""))).strip().casefold()

    raw_author = record.get("author", "")
    if isinstance(raw_author, dict):
        normalized_author = str(raw_author.get("login", "")).strip().casefold()
    else:
        normalized_author = str(raw_author).strip().casefold()

    raw_labels = record.get("labels", [])
    if isinstance(raw_labels, str):
        normalized_labels = {label.strip().casefold() for label in raw_labels.split(",") if label.strip()}
    else:
        normalized_labels = {
            str(label.get("name", "") if isinstance(label, dict) else label).strip().casefold()
            for label in raw_labels
            if str(label.get("name", "") if isinstance(label, dict) else label).strip()
        }

    search_blob = " ".join(
        [
            str(record.get("title", "")),
            str(record.get("body", "")),
            str(record.get("head", record.get("headRefName", ""))),
            str(record.get("base", record.get("baseRefName", ""))),
        ]
    ).casefold()

    if state and normalized_state != state.casefold():
        return False
    if base and normalized_base != base.casefold():
        return False
    if head and normalized_head != head.casefold():
        return False
    if author and normalized_author != author.casefold():
        return False
    if labels:
        required_labels = {label.casefold() for label in labels}
        if not required_labels.issubset(normalized_labels):
            return False
    if search and search.casefold() not in search_blob:
        return False

    return True


def _select_batch(pull_request_numbers: list[int], batch_size: int | None, batch_index: int) -> tuple[list[int], int]:
    if batch_size is None:
        return pull_request_numbers, 1

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if batch_index <= 0:
        raise ValueError("batch_index must be positive")

    start = (batch_index - 1) * batch_size
    selected = pull_request_numbers[start : start + batch_size]
    if not selected:
        raise ValueError("Selected batch is empty")

    batch_count = (len(pull_request_numbers) + batch_size - 1) // batch_size
    return selected, batch_count


class GitHubCLI:
    def __init__(self, dry_run: bool = False, max_attempts: int = 3, backoff_seconds: float = 1.0) -> None:
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

    def merge_pull_request(
        self,
        repo: str,
        pull_request_number: int,
        merge_method: str = "squash",
        delete_branch: bool = True,
    ) -> str:
        base_args = [
            "gh",
            "pr",
            "merge",
            str(pull_request_number),
            "--repo",
            repo,
            f"--{merge_method}",
        ]
        if delete_branch:
            base_args.append("--delete-branch")

        admin_args = [*base_args, "--admin"]
        if self.dry_run:
            print("DRY-RUN:", " ".join(admin_args))
            return "dry-run"

        try:
            self._run(admin_args)
            return "admin"
        except RuntimeError as admin_error:
            try:
                self._run(base_args)
                return "fallback"
            except RuntimeError as fallback_error:
                raise RuntimeError(
                    f"Failed to merge PR #{pull_request_number}: admin={admin_error}; fallback={fallback_error}"
                ) from fallback_error

    def list_pull_requests(
        self,
        repo: str,
        state: str = "open",
        base: str | None = None,
        head: str | None = None,
        author: str | None = None,
        labels: list[str] | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        args = [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--json",
            "number,title,state,baseRefName,headRefName,author,labels",
            "--limit",
            str(limit),
            "--state",
            state,
        ]
        if base:
            args.extend(["--base", base])
        if head:
            args.extend(["--head", head])
        if author:
            args.extend(["--author", author])
        for label in labels or []:
            args.extend(["--label", label])
        if search:
            args.extend(["--search", search])

        result = self._run(args)
        data = json.loads(result.stdout or "[]")
        if not isinstance(data, list):
            raise ValueError("Expected gh pr list to return a JSON list")
        return [_normalize_record(record) for record in data]


def merge_pull_requests(
    repo: str = DEFAULT_REPO,
    pull_request_numbers: list[int] | None = None,
    pull_request_data_file: str | None = None,
    state: str | None = None,
    base: str | None = None,
    head: str | None = None,
    author: str | None = None,
    labels: list[str] | None = None,
    search: str | None = None,
    limit: int = 100,
    batch_size: int | None = None,
    batch_index: int = 1,
    dry_run: bool = False,
    gh: GitHubCLI | None = None,
) -> dict[str, Any]:
    github = gh or GitHubCLI(dry_run=dry_run)

    if pull_request_numbers:
        numbers = _normalize_pull_request_numbers(pull_request_numbers)
    else:
        loaded_records = _load_records(pull_request_data_file)
        if loaded_records is not None:
            filtered_records = [
                _normalize_record(record)
                for record in loaded_records
                if _match_pull_request_record(
                    _normalize_record(record),
                    state=state,
                    base=base,
                    head=head,
                    author=author,
                    labels=labels,
                    search=search,
                )
            ]
            numbers = _normalize_pull_request_numbers(records=filtered_records)
        else:
            listed_records = github.list_pull_requests(
                repo,
                state=state or "open",
                base=base,
                head=head,
                author=author,
                labels=labels,
                search=search,
                limit=limit,
            )
            numbers = _normalize_pull_request_numbers(records=listed_records)

    selected_numbers, batch_count = _select_batch(numbers, batch_size, batch_index)

    results = []
    for pull_request_number in selected_numbers:
        strategy = github.merge_pull_request(repo, pull_request_number)
        results.append({"number": pull_request_number, "strategy": strategy})

    return {
        "repo": repo,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "batch_size": batch_size,
        "pull_request_count": len(results),
        "pull_requests": results,
        "total_candidates": len(numbers),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge GitHub pull requests safely")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--pr", dest="pull_request_numbers", action="append", type=int)
    parser.add_argument("--pr-data-file")
    parser.add_argument("--state", default="open")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--author")
    parser.add_argument("--label", dest="labels", action="append")
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--batch-index", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = merge_pull_requests(
        repo=args.repo,
        pull_request_numbers=args.pull_request_numbers,
        pull_request_data_file=args.pr_data_file,
        state=args.state,
        base=args.base,
        head=args.head,
        author=args.author,
        labels=args.labels,
        search=args.search,
        limit=args.limit,
        batch_size=args.batch_size,
        batch_index=args.batch_index,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "batch_count": result["batch_count"],
                "batch_index": result["batch_index"],
                "repo": result["repo"],
                "pull_request_count": result["pull_request_count"],
                "pull_request_numbers": [item["number"] for item in result["pull_requests"]],
                "total_candidates": result["total_candidates"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())