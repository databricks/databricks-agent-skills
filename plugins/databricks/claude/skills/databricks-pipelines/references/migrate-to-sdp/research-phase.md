# Phase 1: Research

You are analyzing an ETL source project to produce a Migration IR
(`migration-plan.yml`) and a human-readable summary (`migration-plan.md`). This phase
is read-only over the source project and writes only those two files into the output
directory. No SDP code is emitted here.

## Source-pluggable

This phase is source-agnostic. Source-specific knowledge (which files to read, how
to enumerate nodes, how to map source materializations to `sdp_type`) lives in the
**source pack** at `references/migrate-to-sdp/sources/<source_type>/`. Before doing any work:

1. **Confirm `source_type`** — the orchestrator should have determined it via
   `references/migrate-to-sdp/00-index.md`. If unset, detect it now or ask the user.
2. **Read the source pack** (mandatory before classifying any node):
   - `references/migrate-to-sdp/sources/<source_type>/` overview.md — what's in a project of this
     type, what files to read.
   - `references/migrate-to-sdp/sources/<source_type>/` decision-rules.md — how source
     materializations map to SDP `sdp_type`.
3. **Read the IR schema**: `references/migrate-to-sdp/ir-schema.yml` — required output structure.

## Workflow

### Reading the source project

Enumerate and read **every** source file, as described in *Reading project files* in `references/migrate-to-sdp.md`. Do
**not** generate or run Python on a cluster (`dbutils.fs`, `spark.read`, `os.listdir`, …) to inspect
the project — this includes directory walking.

- **Local checkout**: list and read the files from disk.
- **Workspace path** (`/Workspace/...`, `/Users/...`): `databricks workspace list` to list a
  directory; `databricks workspace export-dir <path> <local-dir>` copies the whole tree locally so
  you can walk it (e.g. `models/**/*.sql`).
- **UC Volume path** (`/Volumes/{catalog}/{schema}/{volume}/...`): `databricks fs ls dbfs:/Volumes/...`
  to list and `databricks fs cp -r dbfs:/Volumes/... <local-dir>` to copy the tree locally.

Steps 1–6 follow the source pack's overview.md (file enumeration is source-specific).
Steps 7–11 are source-agnostic.

1. Read project config files per the source pack overview.
2. Enumerate all source artifacts (models, snapshots, seeds, mappings, tasks, etc.)
   per the source pack overview.
3. Read schema/test/source declarations per the source pack overview.
4. Read templating helpers (macros, includes, dependent files) per the source pack
   overview.
5. Read snapshot-equivalent constructs (DBT snapshots, Snowflake streams, etc.).
6. Read static reference data (DBT seeds, Snowflake reference tables loaded from
   files, etc.).
7. **Classify each node** using the source pack's decision-rules.md:
   - Assign `sdp_type`.
   - Set `output_format` (sql by default; python only when source-specific rules
     require it).
   - Assess confidence (omit when high; include only for medium/low).
   - Write `notes` for the generate phase about anything tricky.
   - Add `manual_review` entries for items requiring human attention before generation
     can proceed correctly.
8. **Build the DAG**: topologically sort nodes into `dag_levels`. Same shape across
   all source types.
9. **Resolve sources**: every external reference (DBT `source('...')`, Snowflake
   external tables, etc.) maps to a fully qualified `catalog.schema.table` in Unity
   Catalog. The source pack overview specifies how to resolve. If unsure, write the
   mapping with a `manual_review` flag.
10. **Write `migration-plan.yml`** to the output directory, conforming to
    `references/migrate-to-sdp/ir-schema.yml`. Set `metadata.source_type` to the detected source
    type. Set `metadata.output_format` and `metadata.pipeline_name` from Step 0.
    Do NOT write `target_catalog`, `target_schema`, or `migration_schema` —
    these are not IR fields.
11. **Write `migration-plan.md`** — a short human-readable summary so the user can
    review without parsing YAML. See "Summary doc" below.

## Confidence (source-agnostic)

- **high** (omit from IR — high is the default): straightforward node, standard
  materialization, no complex templating, all references resolved.
- **medium**: some templating but expandable, common third-party helpers, all
  dependencies clear.
- **low**: complex custom templating, dynamic SQL, heavy conditionals, unsupported
  packages.

The source pack's decision-rules.md may add source-specific signals that nudge a
node up or down a confidence band — defer to the pack.

## Notes field

`notes` is the escape hatch for guidance the generate phase needs that doesn't fit
structured fields. Examples (DBT-flavored — equivalent patterns apply for other
sources):

- "Uses dbt_utils.surrogate_key — convert to `sha2(concat_ws('|', ...))`"
- "Source has CDC feed enabled, use streaming read"
- "Multiple branches behind `is_incremental()` — convert non-incremental branch"
- "updated_at column available for sequence_by"

## Summary doc (`migration-plan.md`)

Write a Markdown file with these sections:

```markdown
# Migration Plan: <source_project_name>

**Source**: <source_type> at <source_project_path>
**Output**: <output_directory>
**Format**: <sql | python>
**Pipeline target**: the pipeline's existing catalog/schema apply at runtime. Adjust by editing the pipeline settings in Phase 2 if a different target is desired.

## Summary

- Total nodes: <N>
- Skipped: <N>
- Needs manual review: <N>

| SDP type          | Count |
| ----------------- | ----- |
| streaming_table   | N     |
| materialized_view | N     |
| temporary_view    | N     |
| auto_cdc          | N     |
| auto_cdc_snapshot | N     |

## Source mappings

| External source       | →   | Unity Catalog table  |
| --------------------- | --- | -------------------- |
| <source-flavored ref> | →   | catalog.schema.table |
| ...                   | →   | ...                  |

## Items needing review

- <node_id>: <issue>
- ...

## Confidence flags

- <node_id> (medium): <one-line reason>
- ...
```

The user reads this file alongside `migration-plan.yml`. Keep it scannable — link
references rather than duplicating content from the YAML.

## Output

Return a short summary back to the conversation:

- Total nodes and breakdown by `sdp_type`.
- Nodes with medium/low confidence.
- Items flagged for manual review.
- Source mappings that need user verification.
- Path to `migration-plan.yml` and `migration-plan.md`.

Then **wait for the user to approve** before moving to Phase 2.
