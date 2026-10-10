# New to Databricks: plain-language guide and guided setup

Read this when the user is a **software, DevOps, or platform engineer who doesn't know Databricks**. Signals: they ask what a catalog or service principal is; they describe their problem in app, Kafka, or Postgres terms; they don't have a table or a service principal yet; or they say "I just want my events in Databricks." Your job is to get them to a working producer **without making them learn Databricks first**.

## How to talk to them
- **Start from their problem**, not from Databricks products. "Let's get your signup events into a table you can query" beats "Let's configure a Unity Catalog managed Delta table."
- **Introduce one term at a time**, with a one-line plain definition the first time you use it (glossary below). Don't paste the whole glossary.
- **Map to what they know**: a three-part table name is like `database.schema.table` in Postgres; a service principal is like a service account or an IAM role.
- **Offer to do the setup for them.** Show each command, **ask before creating anything**, run it, and verify it worked.
- **Keep Databricks UI detours to a minimum.** Use the CLI and SQL where possible, and point to the UI only for things the CLI can't do (for example the Workspace access entitlement).

## Glossary
Brief definitions to introduce as needed:
- **Workspace:** your Databricks environment (like an AWS account)
- **Workspace URL/ID:** login address and the number after `o=` in the URL
- **Region:** where the workspace runs; Zerobus endpoints are per region
- **Unity Catalog / Catalog / schema / table:** three-level naming; `catalog.schema.table` is like `database.schema.table` in Postgres
- **Managed Delta table:** Databricks stores it; you query with SQL
- **Service principal:** non-human identity for your producer (like a service account)
- **OAuth client ID and secret:** SP's machine credentials (like an API key pair)
- **Grants:** permissions; `USE CATALOG`, `USE SCHEMA` let the SP find the table; `MODIFY` and `SELECT` let it write and read
- **Workspace access entitlement:** switch on the SP that allows workspace access; Zerobus requires it
- **Zerobus endpoint:** the address your producer sends to: `<workspace-id>.zerobus.<region>.cloud.databricks.com`
- **Durable vs queryable:** durable = safely stored (ack sent); queryable = appears in table (~5 seconds later)

## Guided first-time setup
Drive these steps yourself. **Ask before each "create."** If the user already has an item, skip that step.

### Step 1: Make sure the CLI can reach the workspace
```bash
databricks auth profiles
databricks current-user me --profile <PROFILE>
```
**Expected:** profile valid, `current-user me` returns identity. Get **workspace ID** and **region** from [authentication.md Step 1](authentication.md#step-1-find-the-workspace-url-workspace-id-region-and-endpoint) (CLI or UI).

### Step 2: Pick where the table will live
```bash
databricks catalogs list --profile <PROFILE>
databricks schemas list <catalog> --profile <PROFILE>
```
Ask: "Which catalog and schema can your team use?" **Don't assume** `main.default` exists or is writable.

### Step 3: Design the table from a sample event
Ask: **"Paste one example event exactly as your app produces it."** Propose a table:
- text → `STRING`; number → `BIGINT` (or `INT`); decimal → `DOUBLE`; boolean → `BOOLEAN`; time → `TIMESTAMP` (epoch microseconds, not string)
- Nested fixed shape → `STRUCT`; nested varying shape → `VARIANT`; list → `ARRAY`
- Make columns **nullable** by default; `NOT NULL` only for required fields (e.g., event ID)
- For unique rows, include stable `event_id` (dedup downstream; see [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates)); for evolving JSON payloads, offer a **rescue column** ([schema-management.md](schema-management.md))

Show the DDL, ask for approval, then create it:
```bash
databricks experimental aitools tools query \
  "CREATE TABLE <catalog>.<schema>.<table> (event_id STRING NOT NULL, user_id STRING, plan STRING, event_time TIMESTAMP)" \
  --profile <PROFILE>
databricks experimental aitools tools discover-schema <catalog>.<schema>.<table> --profile <PROFILE>
```
**Expected:** `discover-schema` lists the columns you proposed.

### Step 4: Create the producer's identity (service principal)
Explain: "Your producer needs its own login so it doesn't use yours. Databricks calls that a service principal." Ask, then run the CLI steps in [authentication.md](authentication.md) (Step 3): create the service principal, create its secret, and **save the secret immediately** (it isn't shown again). Ask the user to confirm the **Workspace access** entitlement in the UI.

### Step 5: Give it permission to write to the table
Follow [Step 4 in authentication.md](authentication.md#step-4-grant-permissions-on-the-table) to grant the service principal permissions on the table.

Then verify:
```bash
databricks experimental aitools tools query "SHOW GRANTS ON TABLE <catalog>.<schema>.<table>" --profile <PROFILE>
```
**Expected:** the application ID has `MODIFY` and `SELECT` on the table. If it only shows `ALL PRIVILEGES`, that isn't enough for Zerobus; the explicit grants are required.

### Step 6: Save the settings for the producer
Write a `.env` file (add it to `.gitignore`) with `ZEROBUS_SERVER_ENDPOINT`, `DATABRICKS_WORKSPACE_URL`, `ZEROBUS_TABLE_NAME`, `DATABRICKS_CLIENT_ID`, and `DATABRICKS_CLIENT_SECRET` (plus `DATABRICKS_WORKSPACE_ID` for REST or Kafka). **Never** put the secret in code.

### Step 7: Build and verify
Return to Step 4 of SKILL.md to write the producer, send a small test batch, and run the verification query. When the rows appear, show the user how to look at them: the same SQL query, or the table in **Catalog Explorer**.

## What happens next
- **"Where's my data?"** → ~5 seconds, then query
- **"Will it keep up?"** → Scales with streams; SDK handles buffering + retries ([how-it-works.md#scaling](how-it-works.md#scaling))
- **"Dashboard?"** → `databricks-aibi-dashboards` skill once flowing

## Sources
- [Use Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-ingest) (workspace URL and ID, table, service principal, grants)
- [What is Unity Catalog?](https://docs.databricks.com/data-governance/unity-catalog/)
- [Service principals](https://docs.databricks.com/admin/users-groups/service-principals)
