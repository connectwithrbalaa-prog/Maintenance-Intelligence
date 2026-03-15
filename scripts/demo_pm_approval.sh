#!/usr/bin/env bash
set -euo pipefail

# Examples:
#   Dev-header fallback (only when MI_DEV_ALLOW_HEADERS=true on the server):
#     BASE_URL=http://localhost:8000 MI_DEV_ALLOW_HEADERS=true ROLE=operator SUBJECT=planner@example.com ./scripts/demo_pm_approval.sh
#
#   Existing bearer token:
#     BASE_URL=https://staging.example.com AUTH_BEARER_TOKEN="$TOKEN" ./scripts/demo_pm_approval.sh
#
#   Keycloak-style token fetch:
#     TOKEN="$(curl -sS -X POST "$KEYCLOAK_TOKEN_URL" \
#       -H 'Content-Type: application/x-www-form-urlencoded' \
#       --data-urlencode 'grant_type=password' \
#       --data-urlencode "client_id=$KEYCLOAK_CLIENT_ID" \
#       --data-urlencode "client_secret=$KEYCLOAK_CLIENT_SECRET" \
#       --data-urlencode "username=$KEYCLOAK_USERNAME" \
#       --data-urlencode "password=$KEYCLOAK_PASSWORD" | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')"
#     BASE_URL=https://staging.example.com AUTH_BEARER_TOKEN="$TOKEN" ./scripts/demo_pm_approval.sh
#
#   Okta-style token fetch:
#     TOKEN="$(curl -sS -X POST "$OKTA_TOKEN_URL" \
#       -H 'Accept: application/json' \
#       -H 'Content-Type: application/x-www-form-urlencoded' \
#       --data-urlencode 'grant_type=client_credentials' \
#       --data-urlencode "client_id=$OKTA_CLIENT_ID" \
#       --data-urlencode "client_secret=$OKTA_CLIENT_SECRET" \
#       --data-urlencode "scope=$OKTA_SCOPE" | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')"
#     BASE_URL=https://staging.example.com AUTH_BEARER_TOKEN="$TOKEN" ./scripts/demo_pm_approval.sh

BASE_URL="${BASE_URL:-http://localhost:8000}"
AUTH_BEARER_TOKEN="${AUTH_BEARER_TOKEN:-}"
API_KEY="${API_KEY:-}"
MI_DEV_ALLOW_HEADERS="${MI_DEV_ALLOW_HEADERS:-false}"
ORG_ID="${ORG_ID:-default-org}"
ROLE="${ROLE:-operator}"
SUBJECT="${SUBJECT:-planner@example.com}"
ASSET_ID="${ASSET_ID:-ASSET-DEMO-001}"
RUN_ID="${RUN_ID:-RUN-DEMO-$(date +%s)}"
RECOMMENDATION_ID="${RECOMMENDATION_ID:-REC-DEMO-$(date +%s)}"
PROPOSAL_TITLE="${PROPOSAL_TITLE:-Bearing wear on ${ASSET_ID}}"
RATIONALE="${RATIONALE:-Demo PM proposal generated from RCA review.}"
APPROVAL_NOTES="${APPROVAL_NOTES:-Approved during staging demo.}"

export RUN_ID RECOMMENDATION_ID ASSET_ID PROPOSAL_TITLE RATIONALE SUBJECT APPROVAL_NOTES

AUTH_HEADERS=()
if [[ -n "${AUTH_BEARER_TOKEN}" ]]; then
  AUTH_HEADERS+=("-H" "Authorization: Bearer ${AUTH_BEARER_TOKEN}")
  echo "NOTE: using bearer-token auth via AUTH_BEARER_TOKEN"
fi

if [[ -n "${API_KEY}" ]]; then
  AUTH_HEADERS+=("-H" "X-API-Key: ${API_KEY}")
  echo "NOTE: using API key auth via X-API-Key"
fi

if [[ "${MI_DEV_ALLOW_HEADERS,,}" == "true" || "${MI_DEV_ALLOW_HEADERS}" == "1" ]]; then
  AUTH_HEADERS+=("-H" "X-Org-Id: ${ORG_ID}")
  AUTH_HEADERS+=("-H" "X-Role: ${ROLE}")
  AUTH_HEADERS+=("-H" "X-Subject: ${SUBJECT}")
  echo "NOTE: sending dev identity headers for ${SUBJECT} (${ROLE} / ${ORG_ID})"
else
  echo "NOTE: not sending dev identity headers; use AUTH_BEARER_TOKEN or API_KEY if auth is required"
fi

require_python() {
  if ! command -v python >/dev/null 2>&1; then
    echo "python is required for JSON parsing" >&2
    exit 1
  fi
}

post_json() {
  local url="$1"
  local body="$2"
  curl -fsS -X POST "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" -d "$body" "$url"
}

get_json() {
  local url="$1"
  curl -fsS "${AUTH_HEADERS[@]}" "$url"
}

require_python

echo
echo "1) Health check"
HEALTH_RESP="$(get_json "${BASE_URL}/healthz")"
echo "${HEALTH_RESP}"

echo
echo "2) Identity check"
WHOAMI_RESP="$(get_json "${BASE_URL}/api/v1/whoami")"
echo "${WHOAMI_RESP}"

echo
echo "3) Create PM proposal for ${ASSET_ID}"
CREATE_BODY="$(python - <<'PY'
import json
import os

payload = {
    "run_id": os.environ["RUN_ID"],
    "recommendation_id": os.environ["RECOMMENDATION_ID"],
    "asset_id": os.environ["ASSET_ID"],
    "title": os.environ["PROPOSAL_TITLE"],
    "rationale": os.environ["RATIONALE"],
    "evidence": ["alarm:demo-high-vibration", "trend:bearing-temp-rise"],
    "immediate_actions": ["Inspect bearings", "Stage replacement parts"],
    "metadata": {
        "source": "demo-script",
        "recommended_interval": "14d",
        "priority": "high",
    },
}
print(json.dumps(payload))
PY
)"
CREATE_RESP="$(post_json "${BASE_URL}/api/v1/agents/pm/advisor/analyze" "${CREATE_BODY}")"
echo "${CREATE_RESP}"
PROPOSAL_ID="$(printf '%s' "${CREATE_RESP}" | python -c 'import sys, json; print(json.load(sys.stdin).get("proposal_id", ""))')"

if [[ -z "${PROPOSAL_ID}" ]]; then
  echo "proposal creation did not return proposal_id" >&2
  exit 1
fi

echo
echo "4) List PM proposals and confirm ${PROPOSAL_ID} is present"
LIST_RESP="$(get_json "${BASE_URL}/api/v1/agents/pm/proposals?limit=10")"
echo "${LIST_RESP}"
export PROPOSAL_ID
LIST_CHECK="$(printf '%s' "${LIST_RESP}" | python -c 'import os, sys, json; proposals=json.load(sys.stdin); target=os.environ["PROPOSAL_ID"]; print("yes" if any(item.get("proposal_id") == target for item in proposals) else "no")')"
if [[ "${LIST_CHECK}" != "yes" ]]; then
  echo "proposal ${PROPOSAL_ID} not found in proposal list" >&2
  exit 1
fi

echo
echo "5) Approve proposal ${PROPOSAL_ID}"
APPROVE_BODY="$(python - <<'PY'
import json
import os

payload = {
    "approved_by": os.environ["SUBJECT"],
    "notes": os.environ["APPROVAL_NOTES"],
}
print(json.dumps(payload))
PY
)"
APPROVE_RESP="$(post_json "${BASE_URL}/api/v1/agents/pm/proposals/${PROPOSAL_ID}/approve" "${APPROVE_BODY}")"
echo "${APPROVE_RESP}"

echo
echo "6) Summarize CMMS handoff"
export APPROVE_RESP
python - <<'PY'
import json
import os

body = json.loads(os.environ["APPROVE_RESP"])
cms = body.get("cms_result") or {}
work_order = cms.get("work_order") or {}

print(f"proposal_id: {body.get('proposal_id')}")
print(f"status: {body.get('status')}")
print(f"org_id: {body.get('org_id')}")
print(f"proposer_subject: {body.get('proposer_subject')}")
print(f"connector: {cms.get('connector')}")
print(f"cms_reference: {cms.get('cms_reference')}")
print(f"work_order_id: {work_order.get('wo_id')}")
print(f"work_order_priority: {work_order.get('priority')}")
PY

echo
echo "Demo flow complete. Review the portal at ${BASE_URL}/portal/pm-approvals or clean up demo data as needed."