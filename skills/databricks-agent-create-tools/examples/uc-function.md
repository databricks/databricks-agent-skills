# Create a Unity Catalog Function

UC functions let agents run custom SQL or Python logic. Expose them as tools via the managed MCP server for UC functions.

## Option 1: SQL function (recommended for data lookups)

Run this in a SQL warehouse or notebook:

```sql
CREATE OR REPLACE FUNCTION catalog.schema.lookup_customer(
  customer_name STRING COMMENT 'Name of the customer to look up'
)
RETURNS STRING
COMMENT 'Returns customer metadata including email and account ID. Use this when the user asks about a specific customer.'
RETURN SELECT CONCAT(
    'Customer ID: ', customer_id, ', ',
    'Email: ', email
  )
  FROM catalog.schema.customers
  WHERE name = customer_name
  LIMIT 1;
```

Via CLI:

```bash
databricks api post /api/2.0/sql/statements --json '{
  "warehouse_id": "<warehouse-id>",
  "statement": "CREATE OR REPLACE FUNCTION catalog.schema.my_func(...) ..."
}' --profile <profile>
```

## Option 2: Python function

```sql
CREATE OR REPLACE FUNCTION catalog.schema.analyze_text(
  text STRING COMMENT 'Text to analyze'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Analyzes text and returns a summary of key entities found.'
AS $$
  # Python code runs in serverless compute
  entities = [word for word in text.split() if word[0].isupper()]
  return f"Found {len(entities)} potential entities: {', '.join(entities[:5])}"
$$;
```

## Writing effective tool descriptions

The `COMMENT` clause is critical — the LLM uses it to decide when to call the tool.

- **Function COMMENT**: Describe what the function does and when to use it
- **Parameter COMMENT**: Describe what values the parameter accepts
- Be specific: "Returns customer email and ID given a customer name" is better than "Looks up customer info"

## Verify

```bash
databricks functions get catalog.schema.my_func --profile <profile>
```

## Next step

Wire the UC function into your agent. See the **add-tools** skill and use `examples/uc-function.yaml` for the `databricks.yml` resource grant.

MCP URL: `{host}/api/2.0/mcp/functions/{catalog}/{schema}` (exposes all functions in the schema) or `{host}/api/2.0/mcp/functions/{catalog}/{schema}/{function_name}` (single function) (OAuth scope for on-behalf-of-user auth: `unity-catalog`)
