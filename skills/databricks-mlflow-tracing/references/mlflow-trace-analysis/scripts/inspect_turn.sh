#!/bin/bash
# Inspect a specific turn (trace) in detail.
#
# Usage: bash inspect_turn.sh <TRACE_ID>

set -euo pipefail

TRACE_ID="$1"
TMP_DIR=$(mktemp -d)
trap "rm -rf \"$TMP_DIR\"" EXIT

# Fetch the full trace (always outputs JSON, no --output flag needed)
mlflow traces get \
  --trace-id "$TRACE_ID" > "$TMP_DIR/turn_detail.json"

echo "=== All spans ==="
jq '.data.spans[] | {name: .name, status: .status.code, parent_span_id: .parent_span_id}' "$TMP_DIR/turn_detail.json"

echo ""
echo "=== Error spans ==="
jq '.data.spans[] | select(.status.code == "STATUS_CODE_ERROR")' "$TMP_DIR/turn_detail.json"

echo ""
echo "=== Assessments ==="
jq '.info.assessments' "$TMP_DIR/turn_detail.json"
