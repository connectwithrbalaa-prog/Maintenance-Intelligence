#!/bin/bash
set -euo pipefail

python -m maintenance_intelligence.release_merges \
    --pr 19 \
    --pr 20 \
    --pr 21 \
    --pr 22 \
    --pr 23 \
    --pr 24 \
    --pr 25 \
    "$@"