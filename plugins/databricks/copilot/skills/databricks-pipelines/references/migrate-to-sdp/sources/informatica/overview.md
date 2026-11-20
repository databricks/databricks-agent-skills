# Informatica Source: Project Overview

What to expect in an Informatica export and which files to read during the
Research phase.

## Two flavors of Informatica

Informatica ships in two product lines. Both produce export files that this
skill can ingest, but the structure differs:

| Flavor                                | File extension   | Root element / key                |
| ------------------------------------- | ---------------- | --------------------------------- |
| **Informatica PowerCenter** (on-prem) | `.xml`           | `<MAPPING>`                       |
| **Informatica Cloud (IICS)**          | `.json` / `.xml` | `"transformations"` / `<mapping>` |

Detect the flavor by inspecting the first non-whitespace token of the export. If
neither marker is present, ask the user which product produced the file.

## Project layout

An Informatica migration project typically contains one of:

```
<informatica_project_root>/
├── *.xml                       # PowerCenter mapping exports (one mapping per file)
├── *.json                      # IICS mapping JSON exports
├── parameters/                 # Optional: .par/.prm files with $$VAR defaults
└── README                      # Optional: deployer notes on session/workflow setup
```

A single export usually contains exactly one mapping (one IR pipeline). Multiple
mappings → multiple IR pipelines.

## Files to read during Research

In order:

1. **The mapping export(s)** — every `.xml` / `.json` mapping file. For each,
   extract:
   - `<MAPPING NAME="...">` — the pipeline / target dataset name.
   - `<SOURCE>` / `"sources"` — input tables with their `DATABASETYPE`,
     `OWNERNAME` (schema), and `<SOURCEFIELD>` list.
   - `<TARGET>` / `"targets"` — output tables with `<TARGETFIELD>` (note `NULLABLE`
     attribute — it becomes an expectation).
   - `<TRANSFORMATION TYPE="...">` / `"transformations"` — every transformation
     node, its `<TRANSFORMFIELD>` ports (with `PORTTYPE`), and its expression
     attributes (`CONDITION`, `JOIN_CONDITION`, `GROUP_BY`, `LOOKUP_TABLE`, etc.).
   - `<CONNECTOR>` / `"links"` — port-to-port connectivity. Walk these to
     reconstruct the dataflow lineage.
   - `<MAPPINGVARIABLE>` — `$$PARAM_NAME` definitions with default values.
   - `<TARGETLOADORDER>` — when multiple targets exist in one mapping, gives
     the loading sequence.
2. **Parameter files** (`.par` / `.prm`) — runtime overrides for `$$PARAM`
   defaults. If present, surface to the user; do not bake values in.
3. **Pre/post-session SQL** (if embedded in the export under `<SESSEXTENSION>`
   or IICS `"preProcessingCommands"`) — keep as comments in the generated file
   or convert to separate pipeline initialization views where possible.

## Informatica artifact kinds and how they map to IR nodes

Every `<TARGET>` (or IICS target) becomes one IR node. The transformation chain
feeding that target collapses into the node's SDP code. Intermediate
transformations are NOT separate IR nodes unless they fan out to multiple
targets (Router) — in which case each downstream group becomes its own node.

| Artifact                             | IR `source_path`      | Notes                                                          |
| ------------------------------------ | --------------------- | -------------------------------------------------------------- |
| Single-target mapping                | the export file path  | One IR node                                                    |
| Multi-target mapping (Router)        | the export file path  | One IR node per Router output group + DEFAULT                  |
| Multi-target mapping (multiple TGTs) | the export file path  | One IR node per `<TARGET>` (use `<TARGETLOADORDER>` for order) |
| Mapplet (`.mplt.xml`)                | the mapplet file path | Convert to a `temporary_view` (SQL) or reusable function       |

`<TRANSFORMATION>` nodes are NOT IR nodes — they are collapsed inline into the
target's SDP code. Two exceptions: **Router**, which fans out to multiple targets
and therefore produces one IR node per output group; and a **Mapplet** defined in
its own `.mplt.xml` file, which becomes a shared `temporary_view` node that the
mappings referencing it consume (matching the Mapplet row in `decision-rules.md`).

## Port types and intermediate calculations

`<TRANSFORMFIELD>` ports carry a `PORTTYPE` attribute:

| PORTTYPE         | Meaning                               | How to handle                                               |
| ---------------- | ------------------------------------- | ----------------------------------------------------------- |
| `INPUT`          | Receives data from upstream           | Resolves to the upstream column                             |
| `OUTPUT`         | Emits data to downstream              | Becomes a column in the `SELECT` / `.select()` output       |
| `INPUT/OUTPUT`   | Pass-through (no transformation)      | Same as `INPUT` — passes the upstream value unchanged       |
| `LOCAL VARIABLE` | Intermediate calculation, not exposed | Inline into downstream expressions; do NOT emit as a column |

LOCAL VARIABLE ports are evaluated in declaration order and can reference
earlier LOCAL VARIABLEs in the same transformation. Treat them as let-bindings
and substitute their expressions into the OUTPUT ports that consume them.

## Source mapping (Informatica-specific)

Each `<SOURCE>` must resolve to a fully qualified `catalog.schema.table` in
Unity Catalog.

> **`SQ_*` is a naming convention, not the table name.** In PowerCenter, sources
> are commonly named with an `SQ_` prefix (the Source Qualifier transformation
> convention; e.g. `SQ_CUSTOMERS`). When `<SOURCE TABLENAME="...">` is present
> on the element, it carries the _actual_ DB table name and takes precedence
> over the `<SOURCE NAME>` attribute. When `TABLENAME` is absent, fall back to
> stripping the `SQ_` prefix from `NAME` to derive the table name, and add the
> node to `manual_review` so the user can confirm.

Resolution sources, in order:

1. The `<SOURCE OWNERNAME="...">` attribute (PowerCenter schema), combined with
   the `DATABASETYPE` for catalog hinting.
2. IICS `"connection.databaseName"` / `"connection.schema"` keys, when present.
3. `$$SRC_SCHEMA` / `$$SRC_CATALOG` mapping variables, when used in the source
   `OWNERNAME` attribute.

If after these resolutions a source still cannot be mapped, add the entry to
`sources[]` with the best guess and add a `manual_review` flag on every node
that references it.
