#!/usr/bin/env bash
# Export dbt models as DBML schemas for the Liam ERD server with dbterd (model_contract algorithm).
#
# Reads target/manifest.json and target/catalog.json (run `uv run dbt docs generate --profiles-dir .` first)
# and writes one schemas/<name>.dbml per export:
#   - tables and column types from the selected models
#   - primary keys from `primary_key` contract constraints
#   - refs from `foreign_key` contract constraints; one-to-one when the FK column has
#     `config.meta.relationship_type: one-to-one`, otherwise many-to-one
#
# Usage:
#   ./scripts/export_erd.sh                                          # all exports below
#   ./scripts/export_erd.sh gold_eshop model.dbt_medallion.fct_      # one custom export: <name> <dbterd --select>
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCHEMAS_DIR="${SCHEMAS_DIR:-$(dirname "$PROJECT_DIR")/schemas}"
cd "$PROJECT_DIR"
mkdir -p "$SCHEMAS_DIR"

for artifact in target/manifest.json target/catalog.json; do
  if [ ! -f "$artifact" ]; then
    echo "$artifact not found. Run \`uv run dbt docs generate --profiles-dir .\` first." >&2
    exit 1
  fi
done

export_erd() {
  uv run dbterd run \
    --artifacts-dir target \
    --algo model_contract \
    --target dbml \
    --entity-name-format table \
    --select "$2" \
    --output "$SCHEMAS_DIR" \
    --output-file-name "$1.dbml"
}

if [ "$#" -eq 2 ]; then
  export_erd "$1" "$2"
else
  export_erd gold_marts schema:gold
  export_erd silver_eshop model.dbt_medallion.slv_eshop__
  export_erd silver_warehouse model.dbt_medallion.slv_wh__
fi
