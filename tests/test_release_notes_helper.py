from maintenance_intelligence.release_notes import build_release_notes


def test_build_release_notes_uses_compare_and_deduplicated_prs(tmp_path) -> None:
    compare_data = {
        "commits": [
            {
                "sha": "1111111aaaa",
                "author": {"login": "alice"},
                "commit": {
                    "message": "feat: add migration smoke test\n\nBody",
                    "author": {"name": "Alice"},
                },
            },
            {
                "sha": "2222222bbbb",
                "author": None,
                "commit": {
                    "message": "fix: clean up release tooling",
                    "author": {"name": "Build Bot"},
                },
            },
            {
                "sha": "3333333cccc",
                "author": {"login": "bob"},
                "commit": {
                    "message": "chore: unmatched commit falls back to commit summary",
                    "author": {"name": "Bob"},
                },
            },
        ]
    }
    commit_pr_map = {
        "1111111aaaa": [
            {"number": 19, "title": "feat: migration smoke", "mergedAt": "2026-03-15T12:00:00Z"}
        ],
        "2222222bbbb": [
            {"number": 19, "title": "feat: migration smoke", "mergedAt": "2026-03-15T12:00:00Z"},
            {"number": 21, "title": "chore: tooling cleanup", "mergedAt": "2026-03-15T13:00:00Z"},
        ],
        "3333333cccc": [],
    }

    compare_path = tmp_path / "compare.json"
    pr_map_path = tmp_path / "pr-map.json"
    compare_path.write_text(__import__("json").dumps(compare_data), encoding="utf-8")
    pr_map_path.write_text(__import__("json").dumps(commit_pr_map), encoding="utf-8")

    output = build_release_notes(
        repo="connectwithrbalaa-prog/Maintenance-Intelligence",
        since_tag="v0.1.0",
        to_tag="v0.2.0",
        compare_data_file=str(compare_path),
        commit_pr_map_file=str(pr_map_path),
    )

    assert "# Maintenance Intelligence v0.2.0" in output
    assert "- feat: migration smoke (#19)" in output
    assert "- chore: tooling cleanup (#21)" in output
    assert "- chore: unmatched commit falls back to commit summary (commit 3333333)" in output
    assert output.count("(#19)") == 1
    assert "- @alice" in output
    assert "- @bob" in output
    assert "- Build Bot" in output