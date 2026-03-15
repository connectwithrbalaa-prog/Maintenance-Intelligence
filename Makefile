.PHONY: setup dev-install fmt lint test test-migrations api run-sim run-ingest run-rca run-wo run-signals export-bad-actors migrate demo-pm-approval

setup:
	python -m pip install --upgrade pip
	pip install -e .[dev,ops]

dev-install: setup

fmt:
	black .
	ruff check . --fix

lint:
	ruff check .
	black --check .

test:
	pytest

test-migrations:
	pytest tests/test_migrate_import.py tests/test_migration_smoke.py

api:
	uvicorn maintenance_intelligence.api.main:app --reload

run-sim:
	python -m maintenance_intelligence.services.simulator

run-ingest:
	python -m maintenance_intelligence.services.ingestion

run-rca:
	python -m maintenance_intelligence.services.rca_agent

run-wo:
	python -m maintenance_intelligence.services.wo_bridge

run-signals:
	python -m maintenance_intelligence.services.signals

export-bad-actors:
	mi-runner export-bad-actors --limit 50

migrate:
	python -m maintenance_intelligence.db.migrate

demo-pm-approval:
	bash scripts/demo_pm_approval.sh
