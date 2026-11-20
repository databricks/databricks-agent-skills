# Informatica → SDP Conversion Rules

Informatica-specific transpilation rules used by the Generate and Repair
phases. The generic SDP target syntax lives in `references/migrate-to-sdp/sdp-syntax.md`; this
file covers the Informatica side of the mapping.

## Transformation → SDP equivalent

| Informatica TRANSFORMATION TYPE | SDP Python                                              | SDP SQL                                                |
| ------------------------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| Source / Source Qualifier       | `spark.read.table(...)` / `spark.readStream.table(...)` | `FROM table` / `FROM STREAM(table)`                    |
| Expression                      | `.withColumn(...)` / `.select(...)`                     | `SELECT col, expr AS alias`                            |
| Filter                          | `.filter(...)` / `.where(...)`                          | `WHERE ...`                                            |
| Joiner                          | `.join(detail, master, on=..., how=...)`                | `JOIN ... ON ...`                                      |
| Lookup (Connected)              | `.join(F.broadcast(lookup), ..., 'left')`               | `LEFT JOIN lookup ON ...`                              |
| Lookup (Unconnected)            | Separate join step; materialize lookup as view          | Same — convert `:LKP.fn(k)` to JOIN                    |
| Aggregator                      | `.groupBy(...).agg(...)`                                | `GROUP BY ...`                                         |
| Router                          | One downstream view per group + DEFAULT                 | One `CREATE VIEW` per group                            |
| Union                           | `.unionByName(allowMissingColumns=True)`                | `UNION ALL`                                            |
| Rank                            | Window function + `row_number()` / `rank()` + filter    | `ROW_NUMBER() OVER (PARTITION BY ...)` + outer `WHERE` |
| Sorter                          | `.orderBy(...)` (usually omit)                          | `ORDER BY ...` (usually omit)                          |
| Normalizer                      | `F.explode(...)` / `F.posexplode(...)`                  | `EXPLODE(...)` / `UNPIVOT`                             |
| Sequence Generator              | `F.monotonically_increasing_id()` or `row_number()`     | `MONOTONICALLY_INCREASING_ID()`                        |
| Update Strategy                 | Drop the transformation; convert to AUTO CDC            | Drop the transformation; convert to AUTO CDC           |
| Transaction Control             | Remove entirely                                         | Remove entirely                                        |
| Stored Procedure                | Translate the SP body to PySpark DataFrame API          | Inline the SP body as Spark SQL                        |
| Mapplet                         | Standalone function returning a DataFrame               | `CREATE TEMPORARY VIEW` / CTE                          |
| Java Transformation             | Translate logic to PySpark DataFrame API                | Translate logic to Spark SQL                           |

In Informatica's Joiner, the **Detail** source is the driving table and **Master**
is the lookup side. Map Detail to the left side and Master to the right side of
the SDP join.

The `Sorted Input` option on Aggregator / Joiner has no equivalent in Spark —
omit it; Spark's optimizer handles ordering.

## Function mapping

Translate Informatica functions to Spark equivalents (applies to both
Python `F.expr` strings and SQL):

| Informatica                                                    | Spark                                                                                                                                                                                                                                               |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `IIF(cond, t, f)`                                              | `CASE WHEN cond THEN t ELSE f END` / `F.when(cond, t).otherwise(f)`                                                                                                                                                                                 |
| `DECODE(val, m1, r1, ..., default)`                            | Chained `CASE WHEN ... END` / `F.when(...).otherwise(default)`                                                                                                                                                                                      |
| `TO_DATE(s, fmt)`                                              | `to_date(s, fmt)` — convert tokens (see Format tokens below)                                                                                                                                                                                        |
| `TO_CHAR(d, fmt)`                                              | `date_format(d, fmt)` — same token conversion                                                                                                                                                                                                       |
| `TO_INTEGER` / `TO_DECIMAL` / `TO_FLOAT` / `TO_BIGINT`         | `CAST(col AS INT / DECIMAL(p,s) / DOUBLE / BIGINT)`                                                                                                                                                                                                 |
| `INSTR(s, substr)`                                             | `instr(s, substr)` (same arg order). For `INSTR(s, substr, start)` use `locate(substr, s, start)` (note: arg order is reversed for `locate`). The 4-arg `INSTR(s, substr, start, occurrence)` has no direct Spark equivalent — flag `manual_review` |
| `SUBSTR(s, start, len)`                                        | `substring(s, start, len)`                                                                                                                                                                                                                          |
| `REPLACECHR(opt, s, chars, repl)`                              | `regexp_replace(...)` or `translate(s, chars, repl)`                                                                                                                                                                                                |
| `REPLACESTR(opt, s, search, repl)`                             | `regexp_replace(s, search, repl)`                                                                                                                                                                                                                   |
| `REG_EXTRACT(s, pat, grp)`                                     | `regexp_extract(s, pat, grp)`                                                                                                                                                                                                                       |
| `REG_MATCH(s, pat)`                                            | `s RLIKE pat` / `col.rlike(pat)`                                                                                                                                                                                                                    |
| `LTRIM` / `RTRIM` / `TRIM`                                     | `ltrim()` / `rtrim()` / `trim()`                                                                                                                                                                                                                    |
| `LPAD` / `RPAD`                                                | `lpad()` / `rpad()`                                                                                                                                                                                                                                 |
| `UPPER` / `LOWER` / `INITCAP`                                  | `upper()` / `lower()` / `initcap()`                                                                                                                                                                                                                 |
| `LENGTH`                                                       | `length()`                                                                                                                                                                                                                                          |
| `CONCAT(s1, s2, ...)`                                          | `concat(s1, s2, ...)` or `concat_ws(sep, ...)`                                                                                                                                                                                                      |
| `s1 \|\| s2` (string concat operator)                          | `concat(s1, s2)` / `concat_ws(...)`                                                                                                                                                                                                                 |
| `SYSDATE` / `SESSSTARTTIME` / `WORKFLOWSTARTTIME`              | `current_timestamp()`                                                                                                                                                                                                                               |
| `ADD_TO_DATE(d, comp, n)` (days)                               | `date_add(d, n)`                                                                                                                                                                                                                                    |
| `ADD_TO_DATE(d, comp, n)` (months)                             | `add_months(d, n)`                                                                                                                                                                                                                                  |
| `ADD_TO_DATE(d, comp, n)` (years)                              | `add_months(d, n*12)`. (`F.expr()` interpolates SQL text, not Python locals — if reaching for `expr`, build the string with an f-string: `F.expr(f"{date_col} + INTERVAL {n_lit} YEARS")`)                                                          |
| `DATE_DIFF(d1, d2, comp)` (days)                               | `datediff(d1, d2)`                                                                                                                                                                                                                                  |
| `DATE_DIFF(d1, d2, comp)` (months)                             | `months_between(d1, d2)`                                                                                                                                                                                                                            |
| `IS_DATE(s)` / `IS_NUMBER(s)` / `IS_SPACES(s)`                 | `to_date(s, fmt) IS NOT NULL` / `CAST(s AS DOUBLE) IS NOT NULL` / `trim(s) = ''`                                                                                                                                                                    |
| `ISNULL(col)`                                                  | `col IS NULL` / `col.isNull()`                                                                                                                                                                                                                      |
| `NVL(v, d)`                                                    | `coalesce(v, d)`                                                                                                                                                                                                                                    |
| `NVL2(v, t, f)`                                                | `CASE WHEN v IS NOT NULL THEN t ELSE f END`                                                                                                                                                                                                         |
| `ROUND` / `TRUNC` / `ABS` / `POWER` / `MOD` / `CEIL` / `FLOOR` | `round()` / `trunc()` / `abs()` / `pow()` / `col % n` / `ceil()` / `floor()`                                                                                                                                                                        |
| `ERROR(msg)` / `ABORT(msg)`                                    | Convert to `@dp.expect_or_fail` / `CONSTRAINT EXPECT ... ON VIOLATION FAIL UPDATE`                                                                                                                                                                  |
| `:LKP.lookup_name(key)`                                        | Rewrite as a JOIN against the lookup table                                                                                                                                                                                                          |

## Date format token conversion

Informatica's date format tokens differ from Spark's. Translate before emitting:

| Informatica | Spark  | Notes                  |
| ----------- | ------ | ---------------------- |
| `YYYY`      | `yyyy` | 4-digit year           |
| `YY`        | `yy`   | 2-digit year           |
| `MM`        | `MM`   | 2-digit month          |
| `MON`       | `MMM`  | Abbreviated month name |
| `MONTH`     | `MMMM` | Full month name        |
| `DD`        | `dd`   | 2-digit day            |
| `DY`        | `E`    | Abbreviated day name   |
| `DAY`       | `EEEE` | Full day name          |
| `HH24`      | `HH`   | 24-hour                |
| `HH12`      | `hh`   | 12-hour                |
| `MI`        | `mm`   | Minute                 |
| `SS`        | `ss`   | Second                 |
| `MS`        | `SSS`  | Milliseconds           |

Apply the conversion to BOTH the format string and any literals being compared
against formatted dates.

## Parameters and variables (`$$NAME`)

Informatica mapping variables (`$$PARAM_NAME`) become SDP pipeline parameters —
keep them parameterized, do not hard-code their values. The form depends on
`output_format` (full rules in `references/migrate-to-sdp/sdp-syntax.md` → Parameters):

| Output format | Pattern                                                            |
| ------------- | ------------------------------------------------------------------ |
| SQL           | `:param_name` (value); `IDENTIFIER(:param_name)` for an identifier |
| Python        | `spark.conf.get("param_name", "default_value")`                    |

Lower-case the parameter name when emitting (drop the `$$` prefix). Each value
arrives as a `STRING`, so `CAST(:param AS <type>)` at the use site when comparing
against a non-string. When `$$NAME` sits in an identifier position (`OWNERNAME`, a
table reference), wrap it in `IDENTIFIER()` for SQL; in Python build the name with
an f-string — a bare `:name` cannot be a table name.

Declare every emitted parameter on the pipeline so it resolves (an undeclared
`:name` fails SQL analysis): SQL output → the pipeline `parameters` field, Python
output → the `configuration` map. Use `<MAPPINGVARIABLE DEFAULT="...">` as the
declared default (and as the second arg to `spark.conf.get`); when there is no
default, declare an empty value for the user to fill in. The Generate phase does
this by editing the pipeline settings.

## NOT NULL constraints → expectations

`<SOURCEFIELD NULLABLE="NOT NULL">` and `<TARGETFIELD NULLABLE="NOT NULL">`
become drop-row expectations on the target:

| Output format | Pattern                                                                   |
| ------------- | ------------------------------------------------------------------------- |
| Python        | `@dp.expect_or_drop("valid_<col>", "<col> IS NOT NULL")`                  |
| SQL           | `CONSTRAINT valid_<col> EXPECT (<col> IS NOT NULL) ON VIOLATION DROP ROW` |

If the same column is marked NOT NULL on both source and target, emit one
expectation (don't duplicate).

## Validation Expression + Router → expectations

A common Informatica pattern computes `IS_VALID_*` flags in an Expression and
then routes "good" vs. "bad" rows via a Router. Collapse this into declarative
expectations rather than preserving the flag-based pattern:

- `IS_VALID_FOO = IIF(condition, 1, 0)` + Router group `GOOD: IS_VALID_FOO = 1`
  → `CONSTRAINT valid_foo EXPECT (condition) ON VIOLATION DROP ROW`
- The Router `DEFAULT` group (catch-all for rejected rows) can be preserved as
  a separate IR node that selects rows where any validation flag is false, if
  the user needs a rejected-records table.

## Update Strategy → AUTO CDC

The Informatica SCD pattern is (Lookup-on-target) → (Expression-compare) →
(Update Strategy with `DD_INSERT` / `DD_UPDATE`) → Target. SDP collapses all of
that into a single `AUTO CDC` flow:

```sql
CREATE OR REFRESH STREAMING TABLE <target>;
CREATE FLOW <target>_cdc AS
  AUTO CDC INTO <target>
  FROM STREAM(<source>)
  KEYS (<unique_key_from_lookup_condition>)
  SEQUENCE BY <change_timestamp_column>
  STORED AS SCD TYPE <1 or 2>;
```

- `KEYS` comes from the `<LOOKUP_CONDITION>` join keys (the columns matching
  source-to-target).
- `SEQUENCE BY` comes from a change-tracking timestamp in the source (commonly
  `MODIFIED_DATE`, `UPDATED_AT`, `LAST_UPD`). If absent, flag for
  `manual_review`.
- `STORED AS SCD TYPE 2` when history-tracking signals are present (see
  `decision-rules.md`); otherwise `TYPE 1`.

If the Update Strategy includes `DD_DELETE`, add
`APPLY AS DELETE WHEN <delete_signal>` — the source must provide an
operation-type column or `_is_deleted` flag for this to work.

## Router → multiple targets

Each Router output group becomes its own downstream view/table. The DEFAULT
group catches rows not matching any other condition:

```sql
CREATE OR REFRESH STREAMING TABLE <group_name>_records
AS SELECT * FROM STREAM(<upstream>)
WHERE <group_condition>;

-- DEFAULT group: negate all other group conditions
CREATE OR REFRESH STREAMING TABLE rejected_records
AS SELECT * FROM STREAM(<upstream>)
WHERE NOT (<g1_condition>) AND NOT (<g2_condition>);
```

## Mapplets

`.mplt.xml` mapplets are reusable groups of transformations:

- **SQL**: convert to a `CREATE TEMPORARY VIEW` or a CTE the caller can reference.
- **Python**: convert to a standalone function that takes a DataFrame and
  returns one — the caller imports and calls it inside its `@dp.table()` /
  `@dp.materialized_view()` body.

## Pre / post-session SQL

Pre-session and post-session SQL commands embedded in `<SESSEXTENSION>` (or
IICS `"preProcessingCommands"`) usually do setup that SDP handles
automatically (truncate target, gather stats, etc.). Convert to one of:

- Drop entirely if the SDP semantics cover it (e.g. SDP handles target
  truncation via materialized-view refresh).
- Convert to a separate pipeline initialization view if it loads reference data.
- Emit as a comment in the generated file with a `TODO` note for the user to
  handle manually.

Never silently drop a pre/post-SQL block — at minimum, surface it as a comment.

## Worked examples

Pattern-specific worked examples are in `examples/`. Load on demand:

- `examples/expression_to_columns.md` — Source + Expression + parameters → columns
- `examples/filter_with_parameters.md` — Filter + mapping variables → SQL streaming table
- `examples/validation_to_expectations.md` — Expression + Router (good/bad) → expectations
- `examples/join_and_aggregator.md` — Filter + Joiner + Aggregator → materialized view
- `examples/update_strategy_to_auto_cdc.md` — Lookup + Expression + Update Strategy → AUTO CDC SCD2
