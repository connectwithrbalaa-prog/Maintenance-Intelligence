import json

import pytest

from maintenance_intelligence.release_merges import GitHubCLI, merge_pull_requests


class RecordingGitHub:
    def __init__(self) -> None:
        self.merges: list[tuple[str, int]] = []

    def merge_pull_request(
        self,
        repo: str,
        pull_request_number: int,
        merge_method: str = "squash",
        delete_branch: bool = True,
    ) -> str:
        assert merge_method == "squash"
        assert delete_branch is True
        self.merges.append((repo, pull_request_number))
        return "recorded"


class QueryingGitHub(RecordingGitHub):
    def __init__(self, records: list[dict[str, object]]) -> None:
        super().__init__()
        self.records = records
        self.list_calls: list[dict[str, object]] = []

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
    ) -> list[dict[str, object]]:
        self.list_calls.append(
            {
                "repo": repo,
                "state": state,
                "base": base,
                "head": head,
                "author": author,
                "labels": labels,
                "search": search,
                "limit": limit,
            }
        )
        return self.records


def test_merge_pull_requests_uses_fixture_input(tmp_path) -> None:
    pull_request_data = [19, {"number": "20"}, 21]
    pull_request_file = tmp_path / "pull-requests.json"
    pull_request_file.write_text(json.dumps(pull_request_data), encoding="utf-8")

    github = RecordingGitHub()
    result = merge_pull_requests(pull_request_data_file=str(pull_request_file), gh=github)

    assert result["pull_request_count"] == 3
    assert github.merges == [
        ("connectwithrbalaa-prog/Maintenance-Intelligence", 19),
        ("connectwithrbalaa-prog/Maintenance-Intelligence", 20),
        ("connectwithrbalaa-prog/Maintenance-Intelligence", 21),
    ]


def test_merge_pull_requests_dry_run_emits_commands(capsys) -> None:
    result = merge_pull_requests(pull_request_numbers=[19, 20], gh=GitHubCLI(dry_run=True))

    assert result["pull_request_count"] == 2
    output = capsys.readouterr().out
    assert (
        "DRY-RUN: gh pr merge 19 --repo connectwithrbalaa-prog/Maintenance-Intelligence --squash --delete-branch --admin"
        in output
    )
    assert (
        "DRY-RUN: gh pr merge 20 --repo connectwithrbalaa-prog/Maintenance-Intelligence --squash --delete-branch --admin"
        in output
    )


def test_merge_pull_requests_filters_and_batches_fixture_input(tmp_path) -> None:
    pull_request_data = [
        {
            "number": 30,
            "title": "RCA stabilize signals",
            "state": "open",
            "base": "main",
            "labels": ["release", "rca"],
        },
        {
            "number": 31,
            "title": "RCA harden reports",
            "state": "open",
            "base": "main",
            "labels": ["release", "rca"],
        },
        {
            "number": 32,
            "title": "RCA improve dashboards",
            "state": "open",
            "base": "main",
            "labels": ["release", "rca"],
        },
        {
            "number": 33,
            "title": "RCA tune health",
            "state": "open",
            "base": "main",
            "labels": ["release", "rca"],
        },
        {
            "number": 34,
            "title": "Docs cleanup",
            "state": "open",
            "base": "main",
            "labels": ["docs"],
        },
    ]
    pull_request_file = tmp_path / "pull-requests.json"
    pull_request_file.write_text(json.dumps(pull_request_data), encoding="utf-8")

    github = RecordingGitHub()
    result = merge_pull_requests(
        pull_request_data_file=str(pull_request_file),
        state="open",
        base="main",
        labels=["release", "rca"],
        search="RCA",
        batch_size=2,
        batch_index=2,
        gh=github,
    )

    assert result["total_candidates"] == 4
    assert result["batch_count"] == 2
    assert result["pull_request_count"] == 2
    assert github.merges == [
        ("connectwithrbalaa-prog/Maintenance-Intelligence", 32),
        ("connectwithrbalaa-prog/Maintenance-Intelligence", 33),
    ]


def test_merge_pull_requests_queries_github_when_no_explicit_input() -> None:
    github = QueryingGitHub(
        [
            {"number": 41},
            {"number": 42},
            {"number": 43},
        ]
    )

    result = merge_pull_requests(
        base="main",
        author="copilot",
        labels=["release"],
        search="stabilization",
        limit=50,
        batch_size=2,
        batch_index=2,
        gh=github,
    )

    assert result["total_candidates"] == 3
    assert result["pull_request_count"] == 1
    assert github.list_calls == [
        {
            "repo": "connectwithrbalaa-prog/Maintenance-Intelligence",
            "state": "open",
            "base": "main",
            "head": None,
            "author": "copilot",
            "labels": ["release"],
            "search": "stabilization",
            "limit": 50,
        }
    ]
    assert github.merges == [("connectwithrbalaa-prog/Maintenance-Intelligence", 43)]


def test_github_cli_falls_back_from_admin_merge(monkeypatch) -> None:
    calls: list[list[str]] = []
    attempts = {"count": 0}

    def fake_run(args, check, capture_output, text, timeout):
        calls.append(args)
        attempts["count"] += 1
        if attempts["count"] == 1:
            return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "admin blocked"})()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("time.sleep", lambda *_args: None)

    github = GitHubCLI(max_attempts=1)
    strategy = github.merge_pull_request("connectwithrbalaa-prog/Maintenance-Intelligence", 19)

    assert strategy == "fallback"
    assert calls[0][-1] == "--admin"
    assert "--admin" not in calls[1]


def test_github_cli_raises_after_both_merge_attempts_fail(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, check, capture_output, text, timeout):
        calls.append(args)
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "permanent failure"})()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("time.sleep", lambda *_args: None)

    github = GitHubCLI(max_attempts=1)
    with pytest.raises(RuntimeError, match=r"Failed to merge PR #19"):
        github.merge_pull_request("connectwithrbalaa-prog/Maintenance-Intelligence", 19)

    assert len(calls) == 2
