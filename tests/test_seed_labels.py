import json

import pytest

from maintenance_intelligence.release_labels import GitHubCLI, labels_for_title, seed_and_tag_issues


class RecordingGitHub:
    def __init__(self) -> None:
        self.created_labels: list[dict[str, str]] = []
        self.applied_labels: list[tuple[int, list[str]]] = []

    def ensure_label(self, repo: str, label: dict[str, str]) -> None:
        self.created_labels.append(label)

    def add_labels(self, repo: str, issue_number: int, labels: list[str]) -> None:
        self.applied_labels.append((issue_number, labels))


def test_seed_and_tag_handles_whitespace_and_multiple_labels(tmp_path) -> None:
    issue_data = [
        {"number": 101, "title": "  Model routing and cost controls  "},
        {"number": 102, "title": "Outcomes analytics (TTR, MTBF/MTTR, acceptance rate)"},
        {"number": 103, "title": "Unmapped title"},
    ]
    issues_file = tmp_path / "issues.json"
    issues_file.write_text(json.dumps(issue_data), encoding="utf-8")

    github = RecordingGitHub()
    result = seed_and_tag_issues(issue_data_file=str(issues_file), gh=github)

    assert result["total_issues"] == 3
    assert github.applied_labels == [
        (101, ["AI/ML", "Scalability"]),
        (102, ["Observability", "UX"]),
    ]
    assert len(github.created_labels) == 5


def test_seed_and_tag_rejects_empty_issue_input(tmp_path) -> None:
    issues_file = tmp_path / "issues.json"
    issues_file.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="No open issues found"):
        seed_and_tag_issues(issue_data_file=str(issues_file), gh=RecordingGitHub())


def test_labels_for_title_deduplicates_overlapping_rules() -> None:
    labels = labels_for_title("Model routing, security, and PII governance")

    assert labels == ["AI/ML", "Scalability", "Security"]


def test_github_cli_retries_before_succeeding(monkeypatch) -> None:
    calls: list[list[str]] = []
    attempts = {"count": 0}

    def fake_run(args, check, capture_output, text, timeout):
        calls.append(args)
        attempts["count"] += 1
        if attempts["count"] < 3:
            return type(
                "Result", (), {"returncode": 1, "stdout": "", "stderr": "temporary failure"}
            )()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("time.sleep", lambda *_args: None)

    github = GitHubCLI()
    github.ensure_label(
        "connectwithrbalaa-prog/Maintenance-Intelligence",
        {"name": "UX", "color": "ff7f00", "description": "Operator endpoints, UI, docs"},
    )

    assert len(calls) == 3


def test_github_cli_raises_after_retry_exhaustion(monkeypatch) -> None:
    def fake_run(args, check, capture_output, text, timeout):
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "permanent failure"})()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("time.sleep", lambda *_args: None)

    github = GitHubCLI(max_attempts=2)
    with pytest.raises(RuntimeError, match="permanent failure"):
        github.add_labels("connectwithrbalaa-prog/Maintenance-Intelligence", 101, ["UX"])
