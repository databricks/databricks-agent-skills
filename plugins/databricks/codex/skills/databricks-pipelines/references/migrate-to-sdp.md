# Migrate ETL Project to Spark Declarative Pipeline

Convert an existing ETL project into a Lakeflow Spark Declarative Pipeline (SDP).
Use this reference when the user asks to migrate, port, or convert an ETL project to
SDP or Lakeflow.

Supported source ETLs today: **DBT** and **Informatica** (PowerCenter XML or
IICS JSON/XML exports). The workflow is structured so additional sources
(Snowflake, etc.) can be added without rewriting the orchestrator — add a
`references/migrate-to-sdp/sources/<source>/` pack and a routing entry in
`references/migrate-to-sdp/00-index.md`.

## Inputs

A single argument is required: a path to the ETL source project. This is a local
directory, a Workspace path (e.g. `/Workspace/Users/.../my_dbt_project/`), or a Unity Catalog
Volume path. Do not start work without this path — ask the user if they did not provide one.

## Reading project files (read this first)

List and read the source project directly from where it lives — starting with the very first
inspection in Step 0, and throughout every later phase:

- **Local checkout**: read the files from disk.
- **Workspace path** (`/Workspace/...`): `databricks workspace list <path>` to list a folder and
  `databricks workspace export <path> --format SOURCE` (or `databricks workspace export-dir` for the
  whole tree) to read files.
- **UC Volume path** (`/Volumes/...`): `databricks fs ls dbfs:/Volumes/...` to list and
  `databricks fs cat dbfs:/Volumes/...` (or `databricks fs cp -r` to a local folder) to read.

Do **not** generate or execute Python on a cluster (`dbutils.fs`, `spark.read`, `os.listdir`, …) to
inspect the source project; the CLI and local reads are direct and avoid a needless cluster round-trip.

## Reference files

This workflow is split into source-agnostic phase docs, an SDP target reference, and
per-source packs. Load each on demand:

| File                                                     | When to load                                                               |
| -------------------------------------------------------- | -------------------------------------------------------------------------- |
| `references/migrate-to-sdp/00-index.md`                                 | Always, at start — to determine `source_type` and which source pack to use |
| `references/migrate-to-sdp/research-phase.md`                           | Phase 1 — analyzing the project and producing the migration plan           |
| `references/migrate-to-sdp/generate-phase.md`                           | Phase 2 — emitting SDP source files                                        |
| `references/migrate-to-sdp/validate-repair-phase.md`                    | Phase 3 — running dry-run, diagnosing, repairing                           |
| `references/migrate-to-sdp/sdp-syntax.md`                               | Phase 2 / 3 — SDP target syntax (Python + SQL)                             |
| `references/migrate-to-sdp/ir-schema.yml`                               | Research and repair — schema for `migration-plan.yml`                      |
| `references/migrate-to-sdp/sources/<source_type>/` overview.md           | Phase 1 — what's in the project, what files to read                        |
| `references/migrate-to-sdp/sources/<source_type>/` decision-rules.md     | Phase 1 — source materialization → `sdp_type`                              |
| `references/migrate-to-sdp/sources/<source_type>/` conversion-rules.md   | Phase 2 / 3 — source-side syntax conversion                                |
| `references/migrate-to-sdp/sources/<source_type>/examples/<pattern>.md` | Phase 2 — worked examples per common pattern                               |

## Workflow

```
[ source detect ] → Research → Generate → ┌── Validate (dry-run) ──┐
                                          │            │           │
                                          │   clean ───┴──► Done   │
                                          │   errors ──► Repair ──┘
                                          └─── loop (max 5) ───────┘
```

### Step 0: Detect source and gather parameters

1. **Detect `source_type`**. Read `references/migrate-to-sdp/00-index.md` and inspect the project
   root the user provided (see *Reading project files* above; never use executed
   code). If detection is
   ambiguous, ask the user. Supported today: `dbt`, `informatica`. Refuse to
   proceed for unsupported sources and surface the detection table.
2. **Ask the user** with one round of questions:
   - **Output format** — `sql` (default, recommended) or `python`.
   - **Output directory** — where to write the migration plan and generated SDP
     files. Default: `<source_project_path>/../migrated_<source_project_name>/`.
     Confirm with the user.

Do NOT ask the user for a target catalog or schema. The migration writes SDP files
into the pipeline and the pipeline's existing catalog/schema apply at runtime. If
the user wants a different target, they adjust it when you show them the proposed
pipeline settings in Phase 2.

### Step 1: Research

Read `references/migrate-to-sdp/research-phase.md`. The phase doc tells you to also load the
source pack's overview.md and decision-rules.md. Research produces TWO
artifacts in the output directory:

1. `migration-plan.yml` — the structured IR (see `references/migrate-to-sdp/ir-schema.yml`).
2. `migration-plan.md` — a human-readable summary the user can review alongside
   the generated SDP source files.

After both files are written, **show the user the summary** (counts by SDP type,
medium/low confidence nodes, items needing manual review, source mappings) and
**wait for explicit approval** before continuing. The user may edit
`migration-plan.yml` directly between phases.

### Step 2: Generate

Read `references/migrate-to-sdp/generate-phase.md`. It tells you to also load the source pack's
conversion-rules.md and `references/migrate-to-sdp/sdp-syntax.md`. Read the original source
files plus the IR; emit one SDP file per non-skipped node into the output
directory.

Once all node files are written, configure the pipeline:

- Update the pipeline settings to set `serverless = true` and the libraries glob
  pointing at the generated source directory — in the bundle's pipeline resource if
  the project uses one, otherwise with `databricks pipelines update` (or
  `databricks pipelines create` if there is no pipeline yet). Show the user the
  proposed settings diff and get confirmation before applying it; if they reject
  it, adjust and try again based on their feedback. If no pipeline exists, use the
  Project Setup workflow in SKILL.md to create one.
- Declare any parameters the generated code references (SQL `:name` → the
  `parameters` field; Python `spark.conf.get` → the `configuration` map) so the
  pipeline resolves them. See `references/migrate-to-sdp/generate-phase.md`.
- Do NOT explicitly set `catalog` or `schema` unless the user told you to. The
  pipeline's existing catalog/schema apply by default. If the user wants a
  different target, they can change it when you show them the proposed settings.

### Step 3: Validate and repair (loop)

Read `references/migrate-to-sdp/validate-repair-phase.md`. The loop:

1. Deploy or upload the generated files, then start a dry run of the migration pipeline. Deploy again after every repair.
2. Wait for the update to complete by reading the update status.
3. Read failures by listing pipeline events and reading event details.
4. **Source-not-found errors are expected during migration** — when the migration
   environment cannot reach the original source data, classify these as expected
   and do NOT enter repair for them. Report them to the user as informational.
5. For real errors, follow the diagnosis workflow in `references/migrate-to-sdp/validate-repair-phase.md`.
   The repair phase decides: code fault (patch the generated file), IR fault
   (revise `migration-plan.yml` and regenerate the affected nodes), or
   infrastructure fault (stop and report).
6. After a repair, jump back to step 1.
7. Stop after 5 unsuccessful repair iterations and surface everything attempted to
   the user.

When the dry-run is clean, report success to the user with the pipeline link and
the list of generated files. The migration is done.

## Constraints

- The Migration IR (`migration-plan.yml`) is the contract between phases. If the
  user edits it manually, respect their edits and regenerate affected nodes.
- Never override decisions in the IR during generation. Only the repair phase may
  change the IR, and only via explicit `ir_amendments`.
- Do NOT pre-collect catalog or schema from the user in Step 0. The pipeline's
  existing catalog/schema apply. The Phase 2 settings confirmation is where the
  user reviews and (if needed) overrides those values.
- Always read `references/migrate-to-sdp/sdp-syntax.md` and the source pack's
  conversion-rules.md before writing or patching SDP code. Do not improvise SDP
  syntax.
- Source-specific knowledge belongs in the source pack, not in this orchestrator
  or the source-agnostic phase docs. If you find yourself wanting to add
  source-specific guidance to a phase doc, that's a signal it should live in the
  pack instead.
