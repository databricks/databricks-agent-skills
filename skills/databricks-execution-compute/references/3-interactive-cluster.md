# Interactive Cluster Execution

**Use when:** You have an existing running cluster and need to preserve state across multiple tool calls, or need Scala/R support.

## When to Choose Interactive Cluster

- Multiple sequential commands where variables must persist
- Scala or R code (serverless only supports Python/SQL)
- Existing running cluster available

## Trade-offs

| Pro | Con |
|-----|-----|
| State persists via `context_id` | Cluster startup ~5 min if not running |
| Near-instant follow-up commands | Costs money while running |
| Scala/R/SQL support | Must manage cluster lifecycle |

## Critical: Never Start a Cluster Without Asking

**Starting a cluster takes 3-8 minutes and costs money.** Always check first:

```bash
databricks clusters list --cluster-sources UI,API --output json | jq '.[] | select(.state == "RUNNING") | {cluster_id, cluster_name, state, cluster_source}'
```

`--cluster-sources UI,API` restricts the list to user-created clusters and excludes job clusters, which dominate the list on busy workspaces.

If no cluster is running, ask the user:
> "No running cluster. Options:
> 1. Start 'my-dev-cluster' (~5 min startup, costs money)
> 2. Use serverless (instant, no setup)
> Which do you prefer?"

## Code Execution Flow (1.2 commands API)

The Databricks CLI doesn't ship a single "run code on a cluster" subcommand. Use the `1.2 commands` API directly via `databricks api`:

1. **Create an execution context** (one per language per cluster; reuse across commands for state).
2. **Submit the command** — returns a `commandId`.
3. **Poll status** until `status == "Finished"` (or `Error`).
4. **(Optional) Destroy the context** when done. Contexts also expire when the cluster terminates.

### 1. Create a context

```bash
CID="1234-567890-abcdef"  # target cluster; reused by every call below
CTX=$(databricks api post /api/1.2/contexts/create --json '{
  "language": "python",
  "clusterId": "'"$CID"'"
}' | jq -r '.id')
echo "$CTX"  # e.g. ctx_abc123
```

Languages: `python`, `scala`, `sql`, `r`. You need one context per language; running `sql` requires a separate context from `python` on the same cluster.

### 2. Submit a command

```bash
CMD=$(databricks api post /api/1.2/commands/execute --json '{
  "language": "python",
  "clusterId": "'"$CID"'",
  "contextId": "'"$CTX"'",
  "command": "import pandas as pd; df = pd.DataFrame({\"a\": [1, 2, 3]}); print(df)"
}' | jq -r '.id')
echo "$CMD"
```

### 3. Poll status and fetch results

The `/api/1.2/commands/status` endpoint takes its parameters in the query string — a JSON body on a GET request gets dropped by the server.

```bash
while :; do
  STATUS=$(databricks api get "/api/1.2/commands/status?clusterId=${CID}&contextId=${CTX}&commandId=${CMD}")
  STATE=$(echo "$STATUS" | jq -r '.status')
  [ "$STATE" = "Finished" ] && break
  [ "$STATE" = "Error" ] && break
  [ "$STATE" = "Cancelled" ] && break
  sleep 2
done
echo "$STATUS" | jq '{status, results: .results}'
```

`.results.resultType` indicates output type:
- `text` — `.results.data` is the captured stdout string.
- `error` — `.results.summary` has the error preamble; `.results.cause` has the traceback.
- `table` — `.results.schema` + `.results.data` (rows).

### 4. Follow-up commands reuse the context

State (variables, imports, `%pip install`-ed packages) persists across commands sharing the same `contextId`:

```bash
CMD2=$(databricks api post /api/1.2/commands/execute --json '{
  "language": "python",
  "clusterId": "'"$CID"'",
  "contextId": "'"$CTX"'",
  "command": "print(df.shape)"
}' | jq -r '.id')
# poll as above
```

### 5. (Optional) Destroy the context

Contexts auto-expire when the cluster terminates. Destroy explicitly when you're done with a session:

```bash
databricks api post /api/1.2/contexts/destroy --json '{
  "clusterId": "'"$CID"'",
  "contextId": "'"$CTX"'"
}'
```

## Language Support

The `language` field on context-create + command-execute controls the runtime:

```bash
# Scala
databricks api post /api/1.2/contexts/create --json '{"language":"scala","clusterId":"..."}'

# SQL
databricks api post /api/1.2/contexts/create --json '{"language":"sql","clusterId":"..."}'

# R
databricks api post /api/1.2/contexts/create --json '{"language":"r","clusterId":"..."}'
```

Each language needs its own context on the same cluster.

## Installing Libraries

Install pip packages directly in the execution context:

```bash
databricks api post /api/1.2/commands/execute --json '{
  "language":"python","clusterId":"...","contextId":"...",
  "command":"%pip install faker"
}'
```

If needed, restart Python in the same context to pick up new packages:

```bash
databricks api post /api/1.2/commands/execute --json '{
  "language":"python","clusterId":"...","contextId":"...",
  "command":"dbutils.library.restartPython()"
}'
```

## Managing Clusters

All cluster lifecycle goes through `databricks clusters`:

```bash
# List all clusters (full output)
databricks clusters list --cluster-sources UI,API --output json

# Get one cluster's state
databricks clusters get <CLUSTER_ID> | jq '{state, cluster_id, cluster_name}'

# Start a cluster (WITH USER APPROVAL ONLY — costs money, 3-8 min startup)
databricks clusters start <CLUSTER_ID>

# Terminate (reversible — cluster definition kept, state lost)
databricks clusters delete <CLUSTER_ID>

# Permanent delete (irreversible)
databricks clusters permanent-delete <CLUSTER_ID>

# Restart
databricks clusters restart <CLUSTER_ID>

# Resize
databricks clusters resize <CLUSTER_ID> --num-workers 4
```

### Create with a full spec

```bash
# With --json, every field goes in the body — including spark_version (no positional arg).
# custom_tags recommended for resource tracking.
databricks clusters create --json '{
  "cluster_name": "my-cluster",
  "spark_version": "15.4.x-scala2.12",
  "node_type_id": "i3.xlarge",
  "num_workers": 2,
  "autotermination_minutes": 60,
  "custom_tags": {"aidevkit_project": "ai-dev-kit"}
}'
```

Discover node types and DBR versions:

```bash
databricks clusters list-node-types | jq '.node_types[] | {node_type_id, memory_mb, num_cores}'
databricks clusters spark-versions   | jq '.versions[] | {key, name}'
```

## Common Issues

| Issue | Solution |
|-------|----------|
| "No running cluster" | Ask user to start or use serverless |
| `Context not found` | Context expired (cluster restarted, or destroyed); create a new one |
| Library not found mid-session | `%pip install <library>`, then `dbutils.library.restartPython()` if needed |
| Command stuck in `Running` | Send `databricks api post /api/1.2/commands/cancel --json '{"clusterId":"...","contextId":"...","commandId":"..."}'` |

## When NOT to Use

Switch to **[Databricks Connect](1-databricks-connect.md)** when:
- Developing Spark code with local debugging
- Want instant iteration without cluster concerns

Switch to **[Serverless Job](2-serverless-job.md)** when:
- No cluster running and user doesn't want to wait
- One-off execution without state needs
