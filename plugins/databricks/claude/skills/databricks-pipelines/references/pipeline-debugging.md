# Debug pipeline failures via update history

Use `databricks-core` for CLI basics and profile selection.

Use this reference when a user asks about pipeline failures, run history, or wants to diagnose why a pipeline is failing or behaving unexpectedly. Every Spark Declarative Pipeline records an **update history** — each run is an "update". Reading that history reveals failure patterns, error messages, and per-update details.

## When to use

- User asks "why is my pipeline failing?"
- User wants to see recent pipeline update history
- User needs to diagnose recurring or intermittent failures
- User asks what changed between a working run and a broken one
- User asks why a successful run did a full recompute or was unexpectedly slow

## Workflow

### Step 1 — Survey the update history

List recent pipeline updates (`databricks pipelines list-updates <pipeline-id>`). Each entry includes `update_id`, `state`, `creation_time`, `cause`, `full_refresh` and `validate_only` (a dry run); reading one update adds its `config`.

Look for patterns: are failures consistent or intermittent, when did they start, and which was the last successful update? The first page of recent updates is usually enough; only page back (`--page-token`) if the failure is older, and avoid scanning the entire history.

### Step 2 — Inspect the failing update

Pick the most recent failed `update_id` and read its update (`databricks pipelines get-update <pipeline-id> <update-id>`) to get the full state, timing, cause, and refresh selections. The response also carries `config`, the pipeline settings snapshot the update ran with.

### Step 3 — Read the errors

List the pipeline events through the REST API, which returns each event's `details` (`databricks pipelines list-pipeline-events` leaves them out), to surface the failing update's errors and warnings, for example `databricks api get "/api/2.0/pipelines/<pipeline-id>/events?max_results=100&filter=level%20in%20('ERROR','WARN')"`. The response is one page of events, newest first across all updates; follow `next_page_token` (as `page_token`; a request with `page_token` may set only `max_results` besides it) if the failing update's events are older. Keep the events whose `origin.update_id` is the failing update (the server-side filter covers level and timestamp, not the update or event type). For any event that warrants deeper inspection, read its full `error` (exception chain) and `details`.

### Step 4 — Compare against the last good run

Find the last successful `update_id` from the update history, then read both the failed and the last-successful update. Diff their `config` snapshots (catalog, schema, serverless, photon, edition, channel, clusters, configuration) and the refresh selections to isolate what changed.

When the issue is a **latency regression** (both updates succeeded but one was substantially slower), compare the rows each flow wrote in the two updates. The `flow_progress` events of each update carry per-flow metrics (`details.flow_progress.metrics.num_output_rows`); list them for the slow and the fast update and compare per flow. You can also query the pipeline's event log with SQL (`SELECT ... FROM event_log('<pipeline-id>') WHERE event_type = 'flow_progress'`). A large increase between the fast and slow run is concrete evidence that upstream data volume grew and drove the slowdown.

### Step 4a — Drill into specific events

1. List pipeline events for the relevant `update_id` through the REST API, as in Step 3, so each event includes its `details`. The update should be in a terminal state (`COMPLETED`, `FAILED`, or `CANCELED`) so the history is complete. Events have timestamps, flow names, event types, and exception details, and each has an `id`.

   - For **failed updates**, filter on `level` to surface errors and warnings.
   - For **completed updates where the issue is behavioral** (e.g. unexpected full recompute, slower-than-expected run), read the update's progress (INFO-level) events too; event type cannot be filtered server-side, so select `flow_progress` and `planning_information` events from the full event list.

2. The useful structure is in each event's `details`:
   - **`flow_definition`** — flow type, input/output datasets, query plan and schema
   - **`dataset_definition`** — dataset type, path, partition columns, schema, and expectations
   - **`planning_information`** — incrementalization technique and optimization insights (e.g. `FULL_RECOMPUTE` causes)
   - **`flow_progress`** — status, metrics (rows written, backlog), and data quality results

| Pattern | What to look for |
| ------- | ---------------- |
| Schema or expectation error | List events → find the relevant event → its `details`: `dataset_definition` (schema, expectations) and `flow_definition` |

### Step 5 — Summarize

Tell the user what failed, when it started, and the likely root cause, then suggest concrete fixes. When you fix the pipeline, follow the run guidance in SKILL.md: do a dry run after the change, then a regular update, and verify it completes; use a full refresh only if the regular update cannot succeed and the user agrees. Do not copy a full refresh from the failed update's settings.

## Common failure patterns

| Pattern                   | Diagnosis                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| All recent updates failed | Read the latest failed update's errors — likely a code or config error                     |
| Intermittent failures     | Compare successful vs failed updates — look for timing, data volume, or config differences |
| Recent regression         | Find the last successful update and diff its config snapshot against the first failure     |
| Latency regression (both runs succeeded) | Compare per-flow `num_output_rows` in the `flow_progress` events of the fast and the slow update to determine whether data volume growth caused the slowdown |

## Notes

Do not poll the update status in a tight loop: status reads return immediately and are not throttled. To wait for an update you started, poll `databricks pipelines get-update` in a single shell loop, as in [2-rapid-iteration-with-cli](2-rapid-iteration-with-cli.md) (every 30 seconds); for an update you did not start, report its current status and re-check only when a fresh state is actually needed.
