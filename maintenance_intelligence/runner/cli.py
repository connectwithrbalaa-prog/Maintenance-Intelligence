import json
import os

import typer

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
    import json
    import uuid

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
    import datetime as dt
    import json

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
@app.command()
def signals():
    """
    Run the signals processor to compute rollups and detect anomalies.
    """
    from maintenance_intelligence.services.signals import signals_processor
    signals_processor()

@app.command()
def rag(path: str, asset_id: str = typer.Option(..., help="Associate ingested chunks to this asset_id"),
        chunk_size: int = typer.Option(1200, help="Max characters per chunk"),
        bulk_mode: bool = typer.Option(False, help="Chunk documents into multiple pieces")):
    """
    Ingest docs into RAG store (doc_chunks with pgvector embeddings).
    Supports .txt, .md, .html files. HTML is converted to text.
    Usage: mi-runner rag --path ./docs --asset-id PUMP-101 --bulk-mode
    """
    from maintenance_intelligence.rag.ingest import ingest_path
    ingest_path(path, asset_id, chunk_size=chunk_size, bulk_mode=bulk_mode)