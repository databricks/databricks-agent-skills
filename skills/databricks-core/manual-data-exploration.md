# Manual Data Exploration

Discover table schemas and run SQL **directly via the CLI**. These commands are
first-class — running an ad-hoc query or profiling a known table with them needs
nothing else.

This is also the **manual fallback** for finding data when Genie One (the
`databricks-data-discovery` skill, or a Genie MCP tool) isn't available, isn't
installed, or can't find the data or answer the question. Otherwise prefer Genie One for natural-language
data questions, locating data you can't pin down, and query generation: it has
governed access to the org's semantic context that this manual path doesn't.

## Finding Tables

When searching by hand, pick a catalog first, then search it by table name. **Don't
search `information_schema` to find tables:** `system.information_schema` spans every
catalog in the metastore and can run for hours, and even one large catalog's
`information_schema` can take many minutes.

1. Take the catalog from the request. Otherwise run
   `databricks catalogs list --limit 50 --profile <PROFILE>`. If it returns 50, the
   metastore is large and the list is in no particular order, so ask the user which
   catalog holds the data. Otherwise skip `system`, `samples` and catalogs whose names
   start with `__` unless the request is about them. Search `hive_metastore` (step 3)
   only if the request is about it or step 2 finds nothing. Search each remaining
   catalog if there are 10 or fewer; if there are more and none is an obvious match, ask
   the user instead of guessing.
2. Search the candidate catalogs by table name, one call per catalog instead of walking
   each schema by schema. It uses the Unity Catalog API, so it needs no SQL warehouse.
   The pattern is case-sensitive and Unity Catalog stores names in lowercase, so use one
   lowercase word from the request as the keyword. To list a whole catalog or schema
   instead, leave out `--table-name-pattern`:

   ```bash
   # Tables whose name contains the keyword (add --schema-name-pattern if you know the schema)
   for c in <CATALOG1> <CATALOG2>; do
     databricks tables list-summaries "$c" --table-name-pattern '%<KEYWORD>%' --limit 50 --profile <PROFILE>
   done

   # Then discover schema for the tables you found
   databricks experimental aitools tools discover-schema <CATALOG>.<SCHEMA>.<TABLE1> <CATALOG>.<SCHEMA>.<TABLE2> --profile <PROFILE>
   ```

   If 50 tables come back, the list is cut off: use a narrower keyword or add
   `--schema-name-pattern`, and drop `--limit` only when the user asks for every match.
   If nothing matches, try a shorter or different keyword before asking the user.
   Objects you can only BROWSE don't appear in `list-summaries`. To look for them, add
   `--include-browse` to `catalogs list`, list the catalog's schemas with
   `databricks schemas list <CATALOG> --include-browse --profile <PROFILE>`, then run
   `databricks tables list <CATALOG> <SCHEMA> --include-browse --profile <PROFILE>` on the
   likely schemas.
3. `list-summaries` doesn't cover `hive_metastore`. For it, list schemas and search the
   likely ones by name:

   ```bash
   databricks experimental aitools tools query "SHOW SCHEMAS IN hive_metastore" --profile <PROFILE>
   databricks experimental aitools tools query "SHOW TABLES IN hive_metastore.<SCHEMA> LIKE '*<KEYWORD>*'" --profile <PROFILE>
   ```

## Identifier Names & Quoting — Read Before Writing Any Query

**Use catalog, schema, and table names EXACTLY as given.** Never normalize them: do not
change a hyphen (`-`) to an underscore (`_`), and do not add or drop characters.
`hello-world` and `hello_world` are *different* catalogs — silently "fixing" the name
produces `NO_SUCH_CATALOG` / `TABLE_OR_VIEW_NOT_FOUND` against an object that does not
exist. (Case is not significant — Unity Catalog stores names lowercase — but there is no
reason to alter what you were given.)

**Hyphens and other special characters are valid in Unity Catalog names.** For catalogs,
only `.`, space, and `/` are disallowed — a hyphen is fine. So a name like `hello-world`
is a real, legal catalog name; do not assume it "must" be an underscore.

**In SQL, backtick-quote any identifier part that contains a character outside
`[a-zA-Z0-9_]`** (hyphens, spaces, etc.), per part. Unquoted, `hello-world` is parsed as
`hello` minus `world`, which is a syntax error. Quote only the parts that need it:

```sql
-- ❌ Renamed the catalog (hyphen → underscore): catalog does not exist
SHOW TABLES IN hello_world.demo

-- ❌ Correct name, but unquoted hyphen → PARSE_SYNTAX_ERROR
SHOW TABLES IN hello-world.demo

-- ✅ Correct name, special-character part backtick-quoted
SHOW TABLES IN `hello-world`.demo

-- ✅ Fully qualified, each special-character part quoted independently
SELECT * FROM `hello-world`.demo.items LIMIT 10
```

**CLI positional arguments are not SQL — pass the literal name, no backticks.** Commands
like `discover-schema CATALOG.SCHEMA.TABLE` and `tables get CATALOG.SCHEMA.TABLE` take the
plain name (e.g. `discover-schema hello-world.demo.items`). Backticks belong only
inside the SQL string of `... tools query "<SQL>"`.

> Note: legacy `hive_metastore` is stricter than Unity Catalog — table names there allow
> only alphanumeric ASCII and underscores, so hyphens are not valid even with backticks.
> This guidance is for Unity Catalog names.

> References (Databricks):
> [Names](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-names) — allowed
> characters in catalog/schema/table names ·
> [SQL identifiers](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-identifiers) —
> backtick-quoting rules for special characters.

## Overview

The `databricks experimental aitools tools` command group provides tools for data discovery and exploration:
- **discover-schema**: Batch discover table metadata, columns, types, sample data, and statistics
- **query**: Execute SQL queries against Databricks SQL warehouses

**When to use this**: Use these commands whenever you need to:
- Discover table schemas and metadata
- Execute SQL queries against warehouse data
- Explore data structure and content
- Validate data or check table statistics

## Prerequisites

1. **Authenticated Databricks CLI** - see [CLI Authentication Guide](databricks-cli-auth.md) for OAuth2 setup and profile configuration
2. **Access to Unity Catalog tables** with appropriate read permissions
3. **SQL Warehouse** (for query command - auto-detected unless `DATABRICKS_WAREHOUSE_ID` is set)

## Discover Schema

Batch discover table metadata including columns, types, sample data, and null counts.

### Command Syntax

```bash
databricks experimental aitools tools discover-schema TABLE... [flags]
```

Tables must be specified in **CATALOG.SCHEMA.TABLE** format.

### What It Returns

For each table, returns:
- Column names and types
- Sample data (5 rows)
- Null counts per column
- Total row count

### Examples

```bash
# Discover schema for a single table
databricks experimental aitools tools discover-schema samples.nyctaxi.trips --profile my-workspace

# Discover schema for multiple tables
databricks experimental aitools tools discover-schema \
  catalog.schema.table1 \
  catalog.schema.table2 \
  --profile my-workspace

# Get JSON output
databricks experimental aitools tools discover-schema \
  samples.nyctaxi.trips \
  --output json \
  --profile my-workspace
```

### Common Use Cases

1. **Understanding table structure before querying**
   ```bash
   databricks experimental aitools tools discover-schema catalog.schema.customer_data --profile my-workspace
   ```

2. **Comparing schemas across multiple tables**
   ```bash
   databricks experimental aitools tools discover-schema \
     catalog.schema.table_v1 \
     catalog.schema.table_v2 \
     --profile my-workspace
   ```

3. **Identifying columns with null values**
   - The null counts help identify data quality issues

## Query

Execute SQL statements against a Databricks SQL warehouse and return results.

### Command Syntax

```bash
databricks experimental aitools tools query "SQL" [flags]
```

### Warehouse Selection

The command **auto-detects** an available warehouse unless:
- `DATABRICKS_WAREHOUSE_ID` environment variable is set
- You specify a warehouse using other configuration methods

To check which warehouse will be used:
```bash
# Get the default warehouse that would be auto-detected
databricks experimental aitools tools get-default-warehouse --profile my-workspace
```

### Output

Returns:
- Query results as JSON
- Row count
- Execution metadata

### Examples

```bash
# Simple SELECT query
databricks experimental aitools tools query \
  "SELECT * FROM samples.nyctaxi.trips LIMIT 5" \
  --profile my-workspace

# Aggregation query
databricks experimental aitools tools query \
  "SELECT vendor_id, COUNT(*) as trip_count FROM samples.nyctaxi.trips GROUP BY vendor_id" \
  --profile my-workspace

# With JSON output
databricks experimental aitools tools query \
  "SELECT * FROM catalog.schema.table WHERE date > '2024-01-01'" \
  --output json \
  --profile my-workspace

# Using specific warehouse
DATABRICKS_WAREHOUSE_ID=abc123 databricks experimental aitools tools query \
  "SELECT * FROM samples.nyctaxi.trips LIMIT 10" \
  --profile my-workspace
```

### Common Use Cases

1. **Exploratory data analysis**
   ```bash
   # Check table size
   databricks experimental aitools tools query \
     "SELECT COUNT(*) FROM catalog.schema.table" \
     --profile my-workspace

   # View sample data
   databricks experimental aitools tools query \
     "SELECT * FROM catalog.schema.table LIMIT 10" \
     --profile my-workspace

   # Get column statistics
   databricks experimental aitools tools query \
     "SELECT MIN(column), MAX(column), AVG(column) FROM catalog.schema.table" \
     --profile my-workspace
   ```

2. **Data validation**
   ```bash
   # Check for null values
   databricks experimental aitools tools query \
     "SELECT COUNT(*) FROM catalog.schema.table WHERE column IS NULL" \
     --profile my-workspace

   # Verify data freshness
   databricks experimental aitools tools query \
     "SELECT MAX(timestamp_column) FROM catalog.schema.table" \
     --profile my-workspace
   ```

3. **Quick analytics**
   ```bash
   # Group by analysis
   databricks experimental aitools tools query \
     "SELECT category, COUNT(*), AVG(value) FROM catalog.schema.table GROUP BY category" \
     --profile my-workspace
   ```

## Workflow: Complete Data Exploration

Here's a typical workflow combining both commands:

```bash
# 1. Discover the schema first
databricks experimental aitools tools discover-schema \
  samples.nyctaxi.trips \
  --profile my-workspace

# 2. Based on discovered columns, run targeted queries
databricks experimental aitools tools query \
  "SELECT vendor_id, payment_type, COUNT(*) as trips, AVG(fare_amount) as avg_fare
   FROM samples.nyctaxi.trips
   GROUP BY vendor_id, payment_type
   ORDER BY trips DESC
   LIMIT 10" \
  --profile my-workspace

# 3. Investigate specific patterns found in the data
databricks experimental aitools tools query \
  "SELECT * FROM samples.nyctaxi.trips
   WHERE fare_amount > 100
   LIMIT 20" \
  --profile my-workspace
```

## Claude Code-Specific Tips

Remember that each Bash command in Claude Code runs in a separate shell:

```bash
# ✅ RECOMMENDED: Use --profile flag
databricks experimental aitools tools discover-schema samples.nyctaxi.trips --profile my-workspace

# ✅ ALTERNATIVE: Chain with &&
export DATABRICKS_CONFIG_PROFILE=my-workspace && \
  databricks experimental aitools tools query "SELECT * FROM samples.nyctaxi.trips LIMIT 5"

# ❌ DOES NOT WORK: Separate export
export DATABRICKS_CONFIG_PROFILE=my-workspace
databricks experimental aitools tools query "SELECT * FROM samples.nyctaxi.trips LIMIT 5"
```

## Flags

Both commands support:

| Flag | Description | Default |
|------|-------------|---------|
| `--profile` | Profile name from ~/.databrickscfg | Default profile |
| `--output` | Output format: `text` or `json` | `text` |
| `--debug` | Enable debug logging | `false` |
| `--target` | Bundle target to use (if applicable) | - |

## Troubleshooting

### Table Not Found

**Symptom**: `Error: TABLE_OR_VIEW_NOT_FOUND` or `NO_SUCH_CATALOG_EXCEPTION`

**Solution**:
1. Verify table name format: `CATALOG.SCHEMA.TABLE`
2. **Names are literal** — a hyphen is not an underscore; don't normalize it.
   See [Identifier Names & Quoting](#identifier-names--quoting--read-before-writing-any-query).
3. Check if you have read permissions on the table
4. List available tables:
   ```bash
   databricks tables list <catalog> <schema> --profile my-workspace
   ```

### Warehouse Not Available

**Symptom**: `Error: No available SQL warehouse found`

**Solution**:
1. Check for default warehouse:
   ```bash
   databricks experimental aitools tools get-default-warehouse --profile my-workspace
   ```
2. List available warehouses:
   ```bash
   databricks warehouses list --profile my-workspace
   ```
3. Set specific warehouse:
   ```bash
   DATABRICKS_WAREHOUSE_ID=<warehouse-id> databricks experimental aitools tools query "SELECT 1" --profile my-workspace
   ```
4. Start a stopped warehouse:
   ```bash
   databricks warehouses start --id <warehouse-id> --profile my-workspace
   ```

### Permission Denied

**Symptom**: `Error: PERMISSION_DENIED`

**Solution**:
1. Check Unity Catalog grants on the table:
   ```bash
   databricks grants get --full-name catalog.schema.table --principal <user-email> --profile my-workspace
   ```
2. Request SELECT permission from your workspace administrator
3. Verify you have warehouse access (USAGE permission)

### SQL Syntax Error

**Symptom**: `Error: PARSE_SYNTAX_ERROR`

**Solution**:
1. Check SQL syntax - use standard SQL
2. **Backtick-quote special-character identifiers** (`` `hello-world`.demo ``).
   See [Identifier Names & Quoting](#identifier-names--quoting--read-before-writing-any-query).
3. Verify column names match schema (use discover-schema first)
4. Ensure proper quoting for string literals
5. Test query incrementally (start simple, add complexity)

## Best Practices

1. **Always discover schema first** - Use `discover-schema` before writing complex queries to understand:
   - Available columns and their types
   - Data distributions and null patterns
   - Sample data for context

2. **Use LIMIT for exploration** - When exploring large tables, always use LIMIT to avoid long-running queries:
   ```bash
   databricks experimental aitools tools query "SELECT * FROM large_table LIMIT 100" --profile my-workspace
   ```

3. **JSON output for parsing** - Use `--output json` when you need to process results programmatically:
   ```bash
   databricks experimental aitools tools query "SELECT * FROM table" --output json --profile my-workspace | jq '.results'
   ```

4. **Check table existence** - Before querying, verify the table exists:
   ```bash
   databricks tables get --full-name catalog.schema.table --profile my-workspace
   ```

5. **Profile usage** - Always specify `--profile` in Claude Code to avoid authentication issues

## Related Commands

- Use `/databricks-dabs` - Deploy SQL, pipeline, and app resources as code
