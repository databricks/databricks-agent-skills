# Source Routing

The `migrate-to-sdp` skill is source-pluggable. The Research, Generate, and
Validate-Repair phase docs are source-agnostic; per-source knowledge lives under
`references/migrate-to-sdp/sources/<source>/`.

## Detect the source

Inspect the project root the user provided by listing and reading it directly (local files, or
`databricks workspace` / `databricks fs` commands for Workspace and UC Volume paths; see
*Reading project files* in `references/migrate-to-sdp.md`). Do not execute project code merely to detect its source type.

| Marker                                                                                                                                                        | source_type   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| `dbt_project.yml` at the project root                                                                                                                         | `dbt`         |
| PowerCenter `.xml` with `<MAPPING>` root; IICS `.json` containing a top-level `"transformations"` array, or IICS `.xml` with a `<mapping>` / `<MAPPING>` root | `informatica` |

If detection is ambiguous (no marker found, or multiple markers), ask the user which
ETL source this project is.

## Source packs

| source_type   | Pack root                         | Status    |
| ------------- | --------------------------------- | --------- |
| `dbt`         | `references/migrate-to-sdp/sources/dbt/`         | Available |
| `informatica` | `references/migrate-to-sdp/sources/informatica/` | Available |

Future source types (Snowflake, Hive metastore, etc.) appear here as additional
rows.
