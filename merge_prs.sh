set -euo pipefail
REPO="connectwithrbalaa-prog/Maintenance-Intelligence"
PRS=(1 2 3 4 5 6 7 8 9)
for pr in "${PRS[@]}"; do
    echo "Merging PR #$pr..."
    gh pr merge "$pr" --repo "$REPO" --squash --delete-branch --admin || gh pr merge "$pr" --repo "$REPO" --squash --delete-branch
  done
echo "All PRs processed."