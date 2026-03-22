# Demo Anchor Autofill

## Purpose
Populate the demo packet with real run and asset IDs once your API has fresh run data.

## Step 1: Pull a primary run id
Use your demo identity headers and call:

curl -s "<BASE_URL>/api/v1/portal/runs?limit=5" \
  -H "x-user-id: <user>" \
  -H "x-user-role: <role>" \
  -H "x-user-org: <org>"

Pick:
- primary_run_id = first item's run_id
- backup_run_id = second item's run_id

## Step 2: Pull asset anchors
For each selected run id call:

curl -s "<BASE_URL>/api/v1/portal/runs/<run_id>" \
  -H "x-user-id: <user>" \
  -H "x-user-role: <role>" \
  -H "x-user-org: <org>"

Pick:
- primary_asset_id = context_meta.asset_id from primary run
- backup_asset_id = context_meta.asset_id from backup run

## Step 3: Verify anchors
Run:

curl -s "<BASE_URL>/api/v1/portal/runs/latest?asset_id=<primary_asset_id>" \
  -H "x-user-id: <user>" \
  -H "x-user-role: <role>" \
  -H "x-user-org: <org>"

Expected:
- 200 with a valid run payload

## Step 4: Fill packet fields
Update:
- docs/DEMO_PACKET_RUN_SHEET.md

Fields:
- Primary run id
- Backup run id
- Primary asset id
- Backup asset id

## Fast fallback
If only one valid run is available:
- use the same run id as both primary and backup
- use the same asset id as both primary and backup
