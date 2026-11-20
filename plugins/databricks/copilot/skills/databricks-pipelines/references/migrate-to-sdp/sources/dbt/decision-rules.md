# DBT → SDP Decision Rules

How DBT materialization concepts map to SDP `sdp_type` values. The Research phase
applies these rules to classify every IR node.

## Materialization → sdp_type

| DBT signal                                                                | SDP `sdp_type`                   | Notes                                                                           |
| ------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| `materialized='view'` referenced only by other models in this project     | `temporary_view`                 | Pipeline-private intermediate                                                   |
| `materialized='view'` referenced outside this project (dashboards, tools) | `materialized_view`              | Must be persisted                                                               |
| `materialized='table'`                                                    | `materialized_view`              | Full recompute batch                                                            |
| `materialized='ephemeral'`                                                | `temporary_view`                 | Or inline CTE if used only once                                                 |
| `materialized='incremental'` + `strategy='append'` (or no strategy)       | `streaming_table`                | Append-only                                                                     |
| `materialized='incremental'` + `strategy='merge'`                         | `auto_cdc` (SCD Type 1)          | Upsert by `unique_key`                                                          |
| `materialized='incremental'` + `strategy='merge'` + tracks history        | `auto_cdc` (SCD Type 2)          | See history-tracking signals below                                              |
| `snapshot` + `strategy='timestamp'`                                       | `auto_cdc` (SCD Type 2)          | Use `updated_at` for `sequence_by`                                              |
| `snapshot` + `strategy='check'`                                           | `auto_cdc_snapshot` (SCD Type 2) | No timestamp column available                                                   |
| Seed (CSV)                                                                | `materialized_view`              | Set `seed_volume_path` so generate emits `read_files()` / `spark.read.csv(...)` |

For a check-strategy snapshot, SQL output is safe only when the underlying source retains immutable, complete snapshots partitioned by an orderable version (for example `snapshot_version`, batch id, or ordered file metadata). Confirm that every version contains the complete key set; treating a partial batch as a snapshot would turn absent keys into deletes. Record the version column and completeness and immutability evidence under `source_meta`. If versions are absent but the source is a complete current-state snapshot, add a `manual_review` entry to confirm lifecycle: a one-time initial load into an empty target can use SQL `AUTO CDC ONCE`, while recurring DBT snapshot behavior requires the Python snapshot API. If the source contains partial batches, add `manual_review` and do not generate snapshot CDC until the migration reconstructs complete snapshots.

**History-tracking signals** (promote `incremental + merge` from SCD Type 1 to
SCD Type 2):

- The model writes to a clearly history-tracking table (`*_history`, `*_scd2`).
- The model has SCD Type 2 columns (`valid_from`, `valid_to`, `is_current`).
- The `notes`, model docs, or `description` indicate history tracking.

Default to SCD Type 1 when these signals are absent.

## CDC hint fields

For `auto_cdc` and `auto_cdc_snapshot` nodes, populate `sdp_cdc_hint`:

- `scd_type`: `1` (current state) or `2` (history) — required.
- Keys are inferred by the generate phase from the DBT `unique_key` config.
- `sequence_by` is inferred from `updated_at` (snapshots) or whichever timestamp the
  DBT config / `notes` indicate.

## Output format choice

Default to `output_format: sql` for all nodes. Override to `python` only when:

- The DBT model has Jinja that cannot be expanded statically (programmatic logic
  beyond simple variable substitution).
- The model uses macros that expand to logic which is naturally Python (e.g. complex
  pivots, dynamic schema generation).
- A specific SDP feature requires Python (sinks, ForEachBatch, custom data sources).
- An `auto_cdc_snapshot` source is a complete current-state snapshot without immutable version partitions, and recurring behavior is required. A one-time initial load can remain SQL with `AUTO CDC ONCE`; partial batches require manual reconstruction, not a snapshot API.

Per-node overrides are possible via `nodes[].output_format`.

## Confidence

- **high** (omit from IR — high is the default): straightforward model, standard
  materialization, no complex Jinja, all refs/sources resolved.
- **medium**: some Jinja but expandable, common macros (dbt_utils, dbt_expectations),
  all dependencies clear.
- **low**: complex custom macros, dynamic SQL, heavy Jinja conditionals, unsupported
  packages.

## When to flag `manual_review`

Add a `manual_review` entry on a node when:

- A custom macro can't be cleanly expanded (no direct SDP equivalent).
- A source mapping is uncertain and the user needs to confirm
  `catalog.schema.table`.
- Multiple `is_incremental()` branches exist and the conversion is non-obvious.
- The model uses a third-party package that has no documented SDP equivalent.

`manual_review` is NOT for confidence — confidence is its own field. Use
`manual_review` for items that need a human decision before generation can proceed
correctly.
