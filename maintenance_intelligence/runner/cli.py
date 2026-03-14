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
