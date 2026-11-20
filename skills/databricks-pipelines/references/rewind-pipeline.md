# Rewind pipeline

## Purpose

Help the user **rewind** a Lakeflow / Spark Declarative Pipeline to an earlier saved state. You fetch rewind points and dataset scope from the backend, present choices **in the conversation**, optionally preview table data at a rewind version, then start a rewind update. Rewind is in Beta.

## Wizard mode (required)

This flow is a **wizard**: at any moment there is **only one question** from you and **only one user response** before the next turn.

- **Never** preview or enumerate upcoming questions upfront.
- After each fetch or user answer, advance **one** decision only.

## When to use

- User asks to rewind a pipeline, restore to a checkpoint, or replay from an earlier point.
- User names the target pipeline (or its ID is in the context).

## Prerequisites (do not skip)

1. **Pipeline ID** known. If not, ask the user which pipeline and stop.
2. **Rewind enabled on the pipeline** (check the pipeline details):
   - `spec.channel` is **`PREVIEW`**.
   - `spec.configuration` includes `pipelines.rewind.betaEnabled` = `"true"`.

If not enabled, explain the pipeline is **not eligible for rewind** and call out exactly what is missing:

- Missing config key `pipelines.rewind.betaEnabled = "true"`.
- Channel is not `PREVIEW`.

Do **not** proactively suggest changing settings. Only edit the pipeline settings if the user explicitly asks to enable rewind after understanding the impact. Enabling rewind is a **one-way** change and **cannot be reverted**.

## Actions

| Action                 | When                                                                                                              |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Read the pipeline details | Pipeline id, channel, configuration; verify prerequisites.                                                        |
| Read the rewind points | Query the pipeline's `event_log()` for `rewind_summary` points (see step B). |
| List the pipeline datasets | From the pipeline source, or the latest update's `dataset_definition` events (scope candidates). |
| Edit the pipeline settings | Enable rewind prerequisites only when the user explicitly asks to proceed.                                        |
| Run a SQL sample query  | Optional preview of a table at `VERSION AS OF restoreVersion` (external tables only; not pipeline-defined views). |
| Start a pipeline update | Start the rewind update once the user confirms (must pass `rewind_spec`; see Execute below).                       |

## Step-by-step flow (internal order — not copy for the user)

### A. Verify prerequisites

Read the pipeline details. If channel or rewind config is wrong, explain the pipeline is currently not eligible for rewind and what is missing. Stop there unless the user explicitly asks to enable rewind; if they do, confirm they accept that this is a one-way change and cannot be reverted, then edit the pipeline settings and re-read details.

### B. Fetch and present rewind points

Each rewind point is a `rewind_summary` event in the pipeline's event log, and the event's `id` is its `rewind_point_id`. List the points of the last 7 days with a SQL query:

```sql
SELECT id AS rewind_point_id, timestamp, message
FROM event_log('<pipeline-id>')
WHERE event_type = 'rewind_summary'
  AND details:rewind_summary.dry_run = true
  AND timestamp > current_timestamp() - INTERVAL 7 DAYS
ORDER BY timestamp DESC;
```

Do not invent rewind point IDs.

**Empty list:** No saved points yet — explain checkpoints are created automatically about every hour once rewind is configured.

Ask the user to pick **one** rewind point (by number).

- **Backing table** lines include `restoreVersion` — previewable (step D).
- **Checkpoint** lines are not table-previewable.

### C. Fetch and present dataset scope

List the pipeline's datasets, from the pipeline source or the latest update's `dataset_definition` events. Filter to datasets **eligible for rewind**:

- `TABLE`
- `MATERIALIZED_VIEW`
- `STREAMING_TABLE`

Present a **numbered list** of eligible datasets (name, type, status). Default assumption: **all eligible datasets selected** unless the user narrows the list.

Ask:

1. Which datasets to include (all, subset by number/name, or confirm all).
2. Whether to **reset all checkpoints** for selected datasets (`reset_checkpoints`, default **true**).

### D. Optional — preview a table version

Only for a chosen rewind point dataset line with `backingTableRestore.restoreVersion` and a three-part table name (`catalog.schema.table`).

Run this query:

```sql
SELECT * FROM catalog.schema.table VERSION AS OF {restoreVersion}
```

Limit ~1000 rows. Summarize row count and a small sample for the user. Pipeline cluster must be running; if not, say preview requires compute and offer to start a dry run / compute first.

### E. Confirm and execute

Summarize: rewind point, dataset names, `reset_checkpoints`. Ask for explicit confirmation.

Start the rewind with a REST call (`databricks api post /api/2.0/pipelines/<pipeline-id>/updates --json '...'`); `databricks pipelines start-update` drops `rewind_point_id`. The request body carries a `rewind_spec`:

```json
{"rewind_spec": {
  "rewind_point_id": "<rewind point id>",
  "datasets": [{"identifier": "<dataset name>", "cascade": false, "reset_checkpoints": <user choice, default true>}]
}}
```

Set exactly one of `rewind_point_id` (a saved point) or `rewind_timestamp` (a time the user gave instead). Rewind points and dry runs also emit `rewind_summary` events, so once the update is running, confirm the rewind by its own `rewind_summary` event: the one for this update whose `details.rewind_summary.dry_run` is `false` (read the events through the REST API, which includes `details`).

On success, tell the user rewind has finished.

## Rewind replay configuration key

`pipelines.rewind.betaEnabled` = `"true"`.
