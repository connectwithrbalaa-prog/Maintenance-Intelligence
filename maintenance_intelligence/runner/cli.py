import typer, json
from .config import Settings
from .core import run

app = typer.Typer(help="Maintenance Intelligence Runner CLI")

@app.command()
def rca(event_id: str):
    s = Settings()
    result = run(event_id, s)
    typer.echo(json.dumps(result))

if __name__ == "__main__":
    app()
@app.command()
def rca_test():
    """
    Trigger a synthetic RCA run (event_id = TEST-RCA-<uuid>) and print the run result.
    """
    import uuid, json
    from .config import Settings
    from .core import run
    s = Settings()
    eid = f"TEST-RCA-{uuid.uuid4().hex[:8]}"
    result = run(eid, s)
    # Write a minimal stdout line friendly to cron parsers
    typer.echo(json.dumps({"event_id": eid, **result}))
@app.command()
def export_bad_actors(limit: int = 50):
    """
    Export bad-actor ranking as JSON to outputs/reports/bad_actors_<date>.json
    """
    import json, datetime as dt
    from maintenance_intelligence.api.reports import bad_actors
    from maintenance_intelligence.runner.config import Settings
    s = Settings()
    rows = bad_actors(limit=limit)  # FastAPI fn is plain python callable
    outdir = getattr(s, "run_summary_dir", "outputs")
    path_dir = os.path.join(outdir, "reports")
    os.makedirs(path_dir, exist_ok=True)
    fname = f"bad_actors_{dt.datetime.utcnow().strftime('%Y-%m-%d')}.json"
    path = os.path.join(path_dir, fname)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    typer.echo(path)

