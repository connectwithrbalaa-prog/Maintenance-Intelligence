import json
import os

from maintenance_intelligence.runner.summaries import write_run_summary


def test_write_run_summary(tmp_path):
    out_dir = tmp_path / "outs"
    path = write_run_summary(str(out_dir), "RUN-123", {"hello": "world"})
    assert os.path.exists(path)
    with open(path) as f:
        data = json.load(f)
    assert data["hello"] == "world"
