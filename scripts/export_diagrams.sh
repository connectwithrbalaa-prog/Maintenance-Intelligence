#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT_DIR/docs/diagrams/src"
OUT_DIR="$ROOT_DIR/docs/diagrams/export"
MERMAID_TMP="/tmp/mermaid-export"
MMDC="$MERMAID_TMP/node_modules/.bin/mmdc"

DIAGRAMS=(
  executive-summary
  executive-summary-short
  architecture-workflow
  user-workflow
  brd-future-state
  brd-future-state-short
  brd-future-state-quarterly
  rca-pm-cmms-sequence
  notification-edge-sequence
)

mkdir -p "$MERMAID_TMP" "$OUT_DIR"

if [[ ! -x "$MMDC" ]]; then
  echo "Installing Mermaid CLI into $MERMAID_TMP ..."
  npm install --prefix "$MERMAID_TMP" --no-package-lock @mermaid-js/mermaid-cli
fi

for name in "${DIAGRAMS[@]}"; do
  in_file="$SRC_DIR/$name.mmd"
  svg_file="$OUT_DIR/$name.svg"
  png_file="$OUT_DIR/$name.png"

  if [[ ! -f "$in_file" ]]; then
    echo "Skipping missing source: $in_file"
    continue
  fi

  echo "Rendering $name -> SVG"
  "$MMDC" -i "$in_file" -o "$svg_file" -b white -t neutral -w 2200

  echo "Rendering $name -> PNG"
  "$MMDC" -i "$in_file" -o "$png_file" -b white -t neutral -w 2200 -s 2
done

echo "Done. Exported diagrams to $OUT_DIR"