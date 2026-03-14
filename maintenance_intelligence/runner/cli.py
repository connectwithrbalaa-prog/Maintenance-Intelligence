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

