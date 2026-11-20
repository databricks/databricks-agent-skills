# Phase 3: Validate and Repair

You are validating the generated SDP pipeline and repairing failures until the dry-run
is clean. This phase loops: validate → diagnose → repair → validate again, up to 5
unsuccessful repair iterations.

## Validate

1. Start a dry run on the migration pipeline.
2. Poll the update status until the update terminates.
3. List pipeline events and then read the event details to fetch errors and diagnostics.

Classify each error:

- **Source-not-found** (`Table not found`, `Catalog not found`, `Schema not found` for
  upstream sources): **expected during migration** — the migration environment may not
  have access to the original source data. Report these to the user as informational.
  Do NOT enter the repair loop for them.
- **Real errors**: anything else — these go through the repair workflow.
- **Infrastructure** (auth, permissions, network): stop and escalate to the user.

If there are no real errors, the dry-run is clean — report success to the user.
The migration is done; no promotion step.

## Repair: root-cause analysis

Every pipeline error is a signal. Before patching anything, determine WHERE the fault
lies. The four classes are:

- **Code fault**: the IR decision was correct, but generated SDP code is wrong.
- **IR fault**: research made the wrong decision, and the error proves it.
- **Both**: IR was wrong AND the code has additional issues.
- **Infrastructure**: environment problem, not a code or decision problem.

Diagnosis order — **always follow this sequence**:

1. Read the error by listing pipeline events and reading the event details — what failed and where.
2. Read the IR node for the failing model in `migration-plan.yml`.
3. Read the generated SDP file for that node.
4. Read the original source file (the node's `source_path`) for that node. The
   source pack at `references/migrate-to-sdp/sources/<source_type>/` conversion-rules.md explains
   that source's templating, references, and tests.
5. **Triangulate**: compare all four to locate the fault class.

## When to challenge the IR

The IR is not sacred. If the evidence warrants it, propose IR amendments rather than
patching code. Specific signals:

The source pack's decision-rules.md describes how that source's materialization
concepts map to `sdp_type`. Use it to judge whether the IR's classification
matches the source definition.

**Challenge `sdp_type` when:**

- "STREAMING TABLE does not support UPDATE" but IR says `streaming_table`
  → re-read the source: does it perform updates/upserts? → IR should be `auto_cdc`.
- "Cannot use STREAM() with this source" but IR says `streaming_table`
  → is the source actually a batch construct? → IR should be `materialized_view`.
- Pipeline hangs or is extremely slow on a streaming_table
  → is this a full-recompute model? → IR should be `materialized_view`.
- AUTO CDC fails with "no changes detected" on every run
  → is this actually append-only? → IR should be `streaming_table`.

**Challenge source mappings when:**

- Data quality failures on a source that works fine in the original ETL → mapping
  points to the wrong table.
- **Do NOT** challenge mappings for "Table/Catalog/Schema not found" — those are
  expected during migration and should already be filtered out before you see them.

**Challenge `sdp_cdc_hint` when:**

- "Sequence column not found" → wrong `sequence_by` hint.
- "Duplicate keys" in SCD Type 2 → wrong keys hint.
- SCD Type 2 producing unexpected history → should be SCD Type 1, or vice versa.

**Challenge `output_format` when:**

- Python generation fails on a complex model but SQL would express it cleanly.
- SQL can't express a pattern that needs Python.

**Challenge `notes` when:**

- The generate phase followed a note that led to wrong code (e.g. "use Auto Loader"
  when the source is actually a table).

## Repair actions

### Code fault (IR is correct)

- Edit the generated `.sql` or `.py` file with the minimum change needed.
- Verify SDP syntax against `references/migrate-to-sdp/sdp-syntax.md` and the source pack's
  `references/migrate-to-sdp/sources/<source_type>/` conversion-rules.md (plus the relevant
  example under `references/migrate-to-sdp/sources/<source_type>/examples/`).

### IR fault (research was wrong)

Apply amendments to `migration-plan.yml`. Each amendment should be of the form:

```yaml
ir_amendments:
  - node_id: stg_orders
    field: sdp_type
    new_value: auto_cdc
    reason: "Source has updates (e.g. DBT incremental_strategy='merge' with unique_key)"
  - node_id: stg_orders
    field: sdp_cdc_hint
    new_value: { scd_type: 1 }
    reason: 'Added CDC hint for the reclassified node'
```

Then **regenerate the affected node files only** (re-run the relevant slice of
Phase 2 — see `references/migrate-to-sdp/generate-phase.md`). Do not regenerate the whole project.

### Infrastructure fault

Stop. Report to the user. Never attempt to fix auth, permissions, or network issues.

## Loop control

After each repair, re-validate (return to "Validate" above). The 5-iteration budget
counts only iterations where you actually applied a repair. If you exhaust the budget:

1. Stop.
2. Surface to the user: the remaining errors, every repair attempted, the diagnosis,
   and which IR amendments (if any) were applied.
3. Ask the user how they want to proceed (intervene manually, skip a node, abandon
   the migration).

## Success hand-off

When a dry-run is clean (no real errors; source-not-found errors reported as expected),
report success to the user with:

- The pipeline ID and its URL (`<workspace-url>/pipelines/<pipeline-id>`).
- The full list of generated files.
- The catalog/schema the pipeline is writing to (read from the current pipeline
  settings, not the IR).

The migration is done. No promotion step.
