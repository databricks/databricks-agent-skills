#!/bin/bash
# Discover the input/output schema from the first trace in a session.
#
# Usage: bash discover_schema.sh <EXPERIMENT_ID> <SESSION_ID> <START_TIME_MS> <END_TIME_MS>

set -euo pipefail

EXPERIMENT_ID="$1"
SESSION_ID="$2"
START_TIME_MS="$3"
END_TIME_MS="$4"
TMP_DIR=$(mktemp -d)
trap "rm -rf \"$TMP_DIR\"" EXIT

# Find the first trace ID in the session
mlflow traces search \
  --experiment-id "$EXPERIMENT_ID" \
  --filter-string 'metadata.`mlflow.trace.session` = "'"$SESSION_ID"'" AND timestamp_ms >= '"$START_TIME_MS"' AND timestamp_ms <= '"$END_TIME_MS" \
  --order-by "timestamp_ms ASC" \
  --no-include-spans \
  --extract-fields 'info.trace_id' \
  --output json \
  --max-results 1 > "$TMP_DIR/first_trace.json"

TRACE_ID=$(jq -er '.traces[0].info.trace_id // empty' "$TMP_DIR/first_trace.json") || {
  echo "No trace found in the requested session and time window" >&2
  exit 1
}
echo "First trace ID: $TRACE_ID"

# Fetch the full trace detail (always outputs JSON, no --output flag needed)
mlflow traces get \
  --trace-id "$TRACE_ID" > "$TMP_DIR/trace_detail.json"

echo ""
echo "=== Root span attribute keys ==="
jq '.data.spans[] | select(.parent_span_id == null) | .attributes | keys' "$TMP_DIR/trace_detail.json"

echo ""
echo "=== Root span inputs ==="
jq '.data.spans[] | select(.parent_span_id == null) | .attributes["mlflow.spanInputs"]' "$TMP_DIR/trace_detail.json"

echo ""
echo "=== Root span outputs ==="
jq '.data.spans[] | select(.parent_span_id == null) | .attributes["mlflow.spanOutputs"]' "$TMP_DIR/trace_detail.json"
