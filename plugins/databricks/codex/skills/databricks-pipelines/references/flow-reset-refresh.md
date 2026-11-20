# Refresh or reset a single flow

Act on one **flow** of a pipeline by starting a pipeline update whose request body names the flows.

## Flow vs. table

A table can be written by **several flows** (e.g. two append flows feeding the same streaming table). `"refresh_selection": [...]` refreshes whole **tables** (all of their flows). Resetting a flow (below) acts only on the named **flow(s)**, leaving the table's other flows alone. Use flow selection only when the user asks to act on a specific flow.

## The two operations

- **Refresh a flow without resetting it** — not available through the public pipelines API. Tell the user, and offer either a table refresh (`"refresh_selection": ["<table>"]`) or a flow reset.
- **Reset and refresh a flow** — reset the flow's streaming checkpoint so it reprocesses its source from the beginning, **without clearing the target table's existing data**: `"reset_checkpoint_selection": ["main.default.bookings_live"]` in the request body, together with the flow's target table in `"refresh_selection": ["main.default.bookings"]`. A reset flow must be in the refresh selection; without a `refresh_selection` the update refreshes the whole pipeline.

Reset is **not** a full refresh: a full refresh drops and rebuilds the whole table (destructive), whereas resetting a flow's checkpoint keeps the table's data intact.

Resetting a flow is not reversible. A reset therefore needs its own explicit confirmation from the user, which nothing can grant on their behalf — the same treatment a table full refresh gets.

## Naming flows

Flow names in `reset_checkpoint_selection` must be **fully qualified** as `catalog.schema.<name>`. A bare name (e.g. `bookings_live` instead of `main.default.bookings_live`) causes the pipeline update to fail. Never abbreviate, drop the catalog/schema, or invent a name — look it up:

- **A table's default flow** (no explicitly named flow): the flow name is the table's fully-qualified name (`catalog.schema.table`). Take the catalog and schema from the pipeline settings (`spec.catalog`, `spec.schema`) unless the table is defined with a fully-qualified name in the source.
- **An explicitly named flow** (`@dp.append_flow(name="…")`, `create_auto_cdc_flow(name="…")`, or SQL `CREATE FLOW …`): take the flow's name from the pipeline source and qualify it with the **target table's** catalog and schema → `catalog.schema.<flow name>`. The pipeline's flow-definition events (full records from the pipeline events REST API, `details.flow_definition`) list each flow with its `output_dataset`.

Examples (pipeline in `main.default`):

- Default flow of streaming table `bookings` → `main.default.bookings`
- Named flow `bookings_live` targeting `bookings` → `main.default.bookings_live`

## Eligibility

Eligible flow types: **append**, **update**, **AutoCDC**, and **AutoCDC from Snapshot** (**MERGE** flows are coming soon). Not eligible: **ONCE**, **REPLACE WHERE**, **REPLACE USING**, and **materialized view** flows — for those, refresh the **table** instead (`"refresh_selection": ["<table>"]`). If the user asks to reset an ineligible flow, explain this and offer to refresh the table.

## Rules

- Pair `reset_checkpoint_selection` with `refresh_selection` naming the reset flows' target tables. Do **not** combine it with a full refresh (`"full_refresh": true`), a rewind (`rewind_spec`), or `full_refresh_selection`.
- Fully-qualify every flow name (`catalog.schema.<name>`) — see **Naming flows** above. Do not pass a bare name.
- Only set `reset_checkpoint_selection` when the user asked to reset. Never reset a flow to work around a failure the user only asked you to refresh; offer the reset and let them choose, exactly as with a full refresh.
