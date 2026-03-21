import json

import pytest

from maintenance_intelligence.release_milestones import GitHubCLI, seed_milestone


class RecordingGitHub:
    def __init__(self) -> None:
        self.milestones: list[tuple[str, str, str]] = []
        self.issues: list[tuple[str, str, dict[str, str]]] = []

    def ensure_milestone(self, repo: str, title: str, description: str) -> None:
        self.milestones.append((repo, title, description))

    def create_issue(self, repo: str, milestone_title: str, issue: dict[str, str]) -> None:
        self.issues.append((repo, milestone_title, issue))


def test_seed_milestone_uses_fixture_input_and_preserves_whitespace_safely(tmp_path) -> None:
    issue_data = [
        {
            "title": "  Model routing and cost controls  ",
            "body": "  First body  ",
            "label": "enhancement",
        },
        {"title": "Operator UX: feedback endpoints + UI stubs", "body": "Second body"},
    ]
    issues_file = tmp_path / "milestone-issues.json"
    issues_file.write_text(json.dumps(issue_data), encoding="utf-8")

    github = RecordingGitHub()
    result = seed_milestone(issue_data_file=str(issues_file), gh=github)

    assert result["issue_count"] == 2
    assert github.milestones[0][1] == "v0.3.0"
    assert github.issues[0][2] == {
        "title": "Model routing and cost controls",
        "body": "First body",
        "label": "enhancement",
    }
    assert github.issues[1][2]["label"] == "enhancement"


def test_seed_milestone_rejects_empty_issue_fixture(tmp_path) -> None:
    issues_file = tmp_path / "empty.json"
    issues_file.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="No issue definitions found"):
        seed_milestone(issue_data_file=str(issues_file), gh=RecordingGitHub())


def test_github_cli_retries_issue_creation(monkeypatch) -> None:
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
    github.create_issue(
        "connectwithrbalaa-prog/Maintenance-Intelligence",
        "v0.3.0",
        {"title": "Model routing and cost controls", "body": "Body", "label": "enhancement"},
    )

    assert len(calls) == 3


def test_github_cli_raises_after_retry_exhaustion(monkeypatch) -> None:
    def fake_run(args, check, capture_output, text, timeout):
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "permanent failure"})()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("time.sleep", lambda *_args: None)

    github = GitHubCLI(max_attempts=2)
    with pytest.raises(RuntimeError, match="permanent failure"):
        github.ensure_milestone(
            "connectwithrbalaa-prog/Maintenance-Intelligence",
            "v0.3.0",
            "Description",
        )
