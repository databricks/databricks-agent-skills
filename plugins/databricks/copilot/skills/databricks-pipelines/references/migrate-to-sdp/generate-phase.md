# Phase 2: Generate

You are transpiling source-project artifacts into SDP source files, guided by the
Migration IR. Your two inputs are:

1. **Migration IR** (`migration-plan.yml`) — the WHAT: `sdp_type`, source mappings,
   CDC hints, notes.
2. **Original source files** — the source-flavored definitions you convert.

The IR carries decisions; you do the conversion using the source pack's rules and
the SDP target syntax reference.

## Source-pluggable

Before generating any code, **read both**:

1. `references/migrate-to-sdp/sdp-syntax.md` — the SDP target reference (Python + SQL forms,
   dataset types, expectations, table properties, reads).
2. `references/migrate-to-sdp/sources/<source_type>/` conversion-rules.md — how this source's
   constructs (templating, references, tests, packages) map onto SDP. Worked
   examples per pattern live in `references/migrate-to-sdp/sources/<source_type>/examples/`;
   load on demand.

`source_type` is set on `metadata.source_type` in the IR.

## Workflow

For each node in the IR (skip nodes with `skip: true`):

1. **Read the IR node** — get `sdp_type`, `output_format`, `sdp_cdc_hint`, `notes`,
   plus any `source_meta` populated by the source pack.
2. **Read the source file** at the node's `source_path`.
3. **Read attached schema/test definitions** (per the source pack's overview.md —
   e.g. DBT `schema.yml`).
4. **Read templating dependencies** the source file references (per the source
   pack — e.g. DBT macros).
5. **Transpile** using `references/migrate-to-sdp/sources/<source_type>/` conversion-rules.md and
   `references/migrate-to-sdp/sdp-syntax.md`:
   - `sdp_type` from the IR is your constraint — never override it.
   - Resolve intra-project references to bare dataset names; resolve external
     references via the IR's `sources[]` mapping.
   - Strip source-specific templating per the source pack's rules.
   - Preserve source parameters/variables as SDP parameters per
     `references/migrate-to-sdp/sdp-syntax.md` → Parameters: SQL → `:name` (with `IDENTIFIER()`
     for identifier positions), Python → `spark.conf.get("name")`. Never hard-code
     a value that was parameterized in the source.
   - Convert source-side data tests to SDP expectations
     (`CONSTRAINT ... EXPECT` / `@dp.expect*`).
   - For `auto_cdc` / `auto_cdc_snapshot` nodes: use `sdp_cdc_hint.scd_type`. The
     source pack tells you how to derive `keys` and `sequence_by` from the source
     definition.
   - For seed/reference-data nodes: use `seed_volume_path` from the IR and emit
     `read_files()` (SQL) or `spark.read.csv(...)` (Python).
   - If a templating construct can't be cleanly converted, emit a `TODO` comment
     in the output rather than guessing.
6. **Write output files**. Mirror the source directory layout:
   `<source_root>/<rel_path>` → `<output_dir>/<rel_path>` with extension swapped to
   `.sql` (or `.py` if `output_format` is `python`).

## Pipeline configuration

Once all node files are written, configure the pipeline:

1. Edit the pipeline settings with:
   - `serverless: true` (all migration pipelines use serverless).
   - `libraries`: glob pointing at the output directory.
   - **Parameters.** Declare every parameter the generated code references, so
     `:name` resolves (an undeclared SQL parameter fails analysis). From the union
     across all files: SQL output → the top-level `parameters` map
     (`{"name": "value"}` with the source-declared default, or an empty string for the user to
     fill in); Python output → the `configuration` map (what `spark.conf.get`
     reads).
   - Do NOT explicitly set `catalog` or `schema`. The pipeline's existing
     catalog/schema apply at runtime. If the user wants a different target,
     they adjust it when you show them the proposed settings for confirmation.
2. If the pipeline settings do not accept `parameters` / `configuration` in this
   environment, leave the parameters in the code and surface the list (with
   defaults) for the user to declare manually — never hard-code them.
3. The pipeline is now ready for Phase 3 (validate).

## Rules

- Never change `sdp_type` — that decision comes from the IR.
- Always read the original source file — the IR intentionally omits compiled SQL.
- Use IR `notes` and `source_meta` for guidance on tricky patterns.
- Use IR `sources[]` for `catalog.schema.table` resolution.
- **Prefer NOT to use `spark.sql()` in Python output** — use the PySpark DataFrame
  API exclusively (`select`, `where`, `filter`, `groupBy`, `agg`, `join`,
  `withColumn`, etc.). If logic is naturally expressed as SQL, set
  `output_format: sql` instead.
