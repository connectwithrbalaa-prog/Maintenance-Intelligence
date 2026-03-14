.PHONY: setup dev-install fmt lint test api run-sim run-ingest run-rca run-wo export-bad-actors migrate

setup:
\tpython -m pip install --upgrade pip
\tpip install -e .[dev]

dev-install: setup

fmt:
\tblack .
\truff check . --fix

lint:
\truff check .
\tblack --check .

test:
\tpytest

api:
\tuvicorn maintenance_intelligence.api.main:app --reload

run-sim:
\tpython -m maintenance_intelligence.services.simulator

run-ingest:
\tpython -m maintenance_intelligence.services.ingestion

run-rca:
\tpython -m maintenance_intelligence.services.rca_agent

run-wo:
\tpython -m maintenance_intelligence.services.wo_bridge

export-bad-actors:
\tmi-runner export-bad-actors --limit 50

migrate:
\tpython -m maintenance_intelligence.db.migrate
