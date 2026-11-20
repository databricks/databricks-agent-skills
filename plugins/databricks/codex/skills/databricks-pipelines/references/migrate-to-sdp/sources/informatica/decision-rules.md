# Informatica → SDP Decision Rules

How Informatica mapping patterns map to SDP `sdp_type` values. The Research
phase applies these rules to classify every IR node.

Unlike DBT, Informatica does not declare materialization on the source itself —
the target's behavior is implied by the transformations feeding it (Update
Strategy, Lookup-on-target, Aggregator) and by the session's load type
(append vs. update vs. truncate-and-reload). Infer `sdp_type` from the
transformation chain, not from a `materialized` keyword.

## Transformation chain → sdp_type

| Informatica signal                                                                            | SDP `sdp_type`            | Notes                                                                         |
| --------------------------------------------------------------------------------------------- | ------------------------- | ----------------------------------------------------------------------------- |
| Source → Filter / Expression → Target (no aggregation, append-only)                           | `streaming_table`         | Append-only ingestion                                                         |
| Source → Aggregator → Target (group-by / sum / count)                                         | `materialized_view`       | Full recompute on each refresh                                                |
| Source → Joiner / Lookup → Expression → Target (no aggregation, append-only)                  | `streaming_table`         | Append-only enrichment                                                        |
| Source → Joiner / Lookup → Aggregator → Target                                                | `materialized_view`       | Aggregated result                                                             |
| Source → Update Strategy with only `DD_UPDATE` / `DD_INSERT` → Target                         | `auto_cdc` (SCD Type 1)   | Upsert behavior                                                               |
| Source → Lookup(target) + Expression(compare) + Update Strategy → Target (with eff-date cols) | `auto_cdc` (SCD Type 2)   | Classic SCD2 pattern, see history-tracking signals below                      |
| Source → Router → multiple Targets                                                            | one node per output group | Each Router group becomes its own IR node; DEFAULT becomes the catch-all node |
| Mapplet (`.mplt.xml`) referenced by a mapping (no own target)                                 | `temporary_view`          | Reusable transformation block                                                 |
| Session configured with "Truncate target before load" + no aggregation                        | `materialized_view`       | Full reload semantics                                                         |

**History-tracking signals** (promote Update Strategy from SCD Type 1 to SCD Type 2):

- The target table has effective-date columns (`EFF_START_DATE`, `EFF_END_DATE`,
  `VALID_FROM`, `VALID_TO`) or a current-row flag (`CURRENT_FLAG`, `IS_CURRENT`).
- The mapping contains a Lookup on the target table that retrieves the existing
  row, followed by an Expression that compares old vs. new column values.
- The target name suggests history (`*_HIST`, `*_HISTORY`, `*_SCD2`, `DIM_*`).

Default to SCD Type 1 when these signals are absent.

## CDC hint fields

For `auto_cdc` and `auto_cdc_snapshot` nodes, populate `sdp_cdc_hint`:

- `scd_type`: `1` (current state) or `2` (history) — required.
- `keys` are inferred from the `<LOOKUP_CONDITION>` join key, the `<TARGETFIELD>`
  marked as primary key, or the `unique_key` column in the Update Strategy
  expression. If multiple candidates exist, list them all and flag for
  `manual_review`.
- `sequence_by` is inferred from the most recent timestamp column in the source
  (commonly `MODIFIED_DATE`, `UPDATED_AT`, `LAST_UPD`, `CHG_DT`). If absent,
  flag for `manual_review`.

## Update Strategy expressions

Update Strategy transformations use `DD_INSERT`, `DD_UPDATE`, `DD_DELETE`,
`DD_REJECT` (or their numeric forms `0`, `1`, `2`, `3`). The strategy expression
determines CDC behavior:

| Pattern                                                                                                                                      | SDP equivalent                                                     |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Only `DD_INSERT`                                                                                                                             | `streaming_table` (no CDC needed)                                  |
| Mix of `DD_INSERT` / `DD_UPDATE` on the same target                                                                                          | `auto_cdc` SCD Type 1 (upsert)                                     |
| All paths emit `DD_INSERT` (new rows AND changed rows produce a new effective-dated insert; history is preserved by never updating in place) | `auto_cdc` SCD Type 2 (history tracking)                           |
| Includes `DD_DELETE`                                                                                                                         | `auto_cdc` with `apply_as_deletes` — requires delete signal column |
| Includes `DD_REJECT` for invalid rows                                                                                                        | Convert reject branch to an expectation with `DROP ROW`            |

## Output format choice

Default to `output_format: sql` for all nodes. Override to `python` only when:

- The mapping uses a Normalizer (unpivot) — Python's `explode` / `posexplode`
  is clearer than SQL `STACK`.
- The mapping uses a Java Transformation — translate to PySpark DataFrame API
  since custom Java logic rarely maps cleanly to SQL.
- The mapping uses `auto_cdc_snapshot` (no SQL-only syntax exists).
- The mapping uses a Sequence Generator that depends on `monotonically_increasing_id()`
  with custom seed/increment logic.
- A Mapplet is parameterized over multiple call sites — a Python function is
  more natural than a static view.

Per-node overrides are possible via `nodes[].output_format`.

## Confidence

- **high** (omit from IR — high is the default): single-target mapping, standard
  transformations (Source / Expression / Filter / Joiner / Aggregator), all
  port connectivity resolved, all `<SOURCE>` resolved to UC tables.
- **medium**: contains Lookup(connected), Router, Sequence Generator, or
  Normalizer; all dependencies clear but the conversion has multiple valid
  shapes.
- **low**: contains Unconnected Lookup (`:LKP.lookup_name(...)` syntax), Java
  Transformation, Stored Procedure, SQL Override on a Source Qualifier with
  vendor-specific syntax, or heavy use of LOCAL VARIABLE chains with
  non-trivial logic.

## When to flag `manual_review`

Add a `manual_review` entry on a node when:

- The mapping has an Unconnected Lookup whose call sites are ambiguous (the
  `:LKP.fn(...)` expression appears in multiple Expression transformations
  with different arguments).
- A Stored Procedure transformation calls a database-specific procedure whose
  body is not included in the export.
- A Java Transformation contains business logic that the model cannot
  confidently translate (rule of thumb: more than ~30 lines of non-trivial
  Java).
- Source mapping is uncertain and the user needs to confirm
  `catalog.schema.table`.
- A Sequence Generator is used as a real surrogate key (not just a row number)
  — Spark's `monotonically_increasing_id()` is not contiguous across partitions
  and may not match Informatica's NEXTVAL semantics.
- The mapping uses `:SP.stored_proc(...)` from an Expression transformation —
  inline SP calls need explicit user confirmation about the procedure's body.
- `<SESSEXTENSION>` pre/post-SQL contains DDL or data loads that affect
  pipeline state outside the mapping itself.

`manual_review` is NOT for confidence — confidence is its own field. Use
`manual_review` for items that need a human decision before generation can
proceed correctly.
