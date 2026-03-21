import json
import datetime as dt
from pathlib import Path


def write_run_summary(dir_path: str, run_id: str, payload: dict) -> str:
    date_dir = Path(dir_path) / dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    out = date_dir / f"{run_id}.json"
    with out.open("w") as f:
        json.dump(payload, f, indent=2)
    return str(out)
