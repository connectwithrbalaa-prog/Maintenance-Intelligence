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


def merge_pull_requests(
    repo: str = DEFAULT_REPO,
    pull_request_numbers: list[int] | None = None,
    pull_request_data_file: str | None = None,
    dry_run: bool = False,
    gh: GitHubCLI | None = None,
) -> dict[str, Any]:
    github = gh or GitHubCLI(dry_run=dry_run)
    numbers = _normalize_pull_request_numbers(pull_request_numbers, _load_records(pull_request_data_file))

    results = []
    for pull_request_number in numbers:
        strategy = github.merge_pull_request(repo, pull_request_number)
        results.append({"number": pull_request_number, "strategy": strategy})

    return {
        "repo": repo,
        "pull_request_count": len(results),
        "pull_requests": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge GitHub pull requests safely")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--pr", dest="pull_request_numbers", action="append", type=int)
    parser.add_argument("--pr-data-file")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = merge_pull_requests(
        repo=args.repo,
        pull_request_numbers=args.pull_request_numbers,
        pull_request_data_file=args.pr_data_file,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "repo": result["repo"],
                "pull_request_count": result["pull_request_count"],
                "pull_request_numbers": [item["number"] for item in result["pull_requests"]],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())