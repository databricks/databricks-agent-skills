# Legacy: Knowledge Assistant & Supervisor Agent

> **Legacy.** Databricks docs: *"This is a legacy offering. For new low-code agents over your documents and data, use Genie Agents. For new agents written in code, use the Agent Bricks CLI."* For new work, use a Genie Agent with a volume ([create-genie-agent.md § Documents](create-genie-agent.md#documents-uc-volumes)). Use this file only to maintain or migrate an **existing** KA / Supervisor Agent.
>
> **Migrating:** KA → a Genie Agent with the same volume (put the KA instructions in the volume `description` + a text instruction). Supervisor over Genie + KA → one Genie Agent with those tables + the volume. Each KA / Supervisor example (`question` + `guidelines`) becomes a Genie benchmark: same question, `"answer": [{"format": "SQL", "content": []}]`, guidelines as the `evaluation_note` (scoring: [create-genie-agent.md § Documents](create-genie-agent.md#documents-uc-volumes)). Then repoint callers to the Agent mode API and drop the KA / MAS endpoints and their `CAN_QUERY` grants.

## Knowledge Assistant (KA)

Document Q&A (RAG) over files in a volume or an existing Vector Search index.

```bash
databricks knowledge-assistants create-knowledge-assistant "Name" "Description"

# Add a source. With --json pass ONLY the parent positionally; display_name / description /
# source_type / the source body go inside the JSON (mixing positionals with --json errors).
databricks knowledge-assistants create-knowledge-source "knowledge-assistants/{ka_id}" --json '{
  "display_name": "Docs", "description": "Documentation files",
  "source_type": "files", "files": {"path": "/Volumes/catalog/schema/volume/"}}'

databricks knowledge-assistants sync-knowledge-sources "knowledge-assistants/{ka_id}"   # re-sync after file changes
databricks knowledge-assistants get-knowledge-assistant "knowledge-assistants/{ka_id}"
databricks knowledge-assistants list-knowledge-assistants
databricks knowledge-assistants delete-knowledge-assistant "knowledge-assistants/{ka_id}"  # irreversible: confirm the id first
```

- **Source types:** `files` → `{"path": "/Volumes/.../folder/"}` (PDF, TXT, MD, DOCX; trailing slash matters) or `index` → `{"index_name": "catalog.schema.idx", "text_col": "content", "doc_uri_col": "source_url"}` (all three fields required; updates automatically, so no `sync-knowledge-sources` call is needed (that's for `files` sources)).
- **Status:** `CREATING` (2–5 min, up to 10) → `ONLINE` → `OFFLINE`.
- **Troubleshooting:** stuck `CREATING` → wait, check quotas and that the path exists. Docs not indexed → format, path, file permissions. Poor answers → well-structured docs, smaller files, clear headings.
- **Examples:** `databricks knowledge-assistants create-example "knowledge-assistants/{ka_id}" --json '{"question": "...", "guidelines": ["..."]}'` (with `--json`, only the parent is positional), plus `list-` / `get-` / `update-` / `delete-example`.
- **Eval:** a `pdf_eval_questions.json` (`{"file.pdf": {"question", "expected_fact"}}`) from [databricks-unstructured-pdf-generation](../../databricks-unstructured-pdf-generation/SKILL.md) validates retrieval.

## Supervisor Agent (MAS)

Native CLI `databricks supervisor-agents` (Beta). Resource paths are `supervisor-agents/{id}`; `list-*` return bare JSON arrays.

```bash
databricks supervisor-agents create-supervisor-agent "My Supervisor" \
  --description "Routes queries to specialized agents" \
  --instructions "Route data questions to analyst, document questions to docs_agent."
# → {name: "supervisor-agents/<uuid>", endpoint_name: "mas-<short>-endpoint", ...}

databricks supervisor-agents list-supervisor-agents | jq '.[] | select(.display_name == "My Supervisor")'
databricks supervisor-agents get-supervisor-agent supervisor-agents/<id>
# Update: UPDATE_MASK + new DISPLAY_NAME are positional
databricks supervisor-agents update-supervisor-agent supervisor-agents/<id> \
  "display_name,description,instructions" "My Supervisor (v2)" --description "..." --instructions "..."
databricks supervisor-agents delete-supervisor-agent supervisor-agents/<id>   # irreversible: confirm the id first
```

**Endpoint readiness:** the serving endpoint takes up to ~10 min to come ONLINE after create (or a structural update); check `databricks serving-endpoints get <endpoint_name>` before querying.

### Tools

`tool_type` goes in `--json` (rejected as a positional with `--json`); the type-specific block's id field differs by type.

```bash
databricks supervisor-agents create-tool supervisor-agents/<id> analyst --json '{
  "tool_type": "genie_space", "description": "SQL analytics on the analytics warehouse",
  "genie_space": {"id": "<genie_space_id>"}}'                       # id from `databricks genie list-spaces`

databricks supervisor-agents create-tool supervisor-agents/<id> docs_agent --json '{
  "tool_type": "knowledge_assistant", "description": "Answers from product documentation",
  "knowledge_assistant": {"knowledge_assistant_id": "<ka_id>"}}'

databricks supervisor-agents list-tools supervisor-agents/<id>
databricks supervisor-agents get-tool    supervisor-agents/<id>/tools/<tool_id>
databricks supervisor-agents delete-tool supervisor-agents/<id>/tools/<tool_id>
```

| `tool_type` | Block | Use for |
|---|---|---|
| `genie_space` | `{"id": "<space_id>"}` | NL → SQL via Genie |
| `knowledge_assistant` | `{"knowledge_assistant_id": "<ka_id>"}` | Document Q&A via a KA |
| `uc_function` | `{"name": "catalog.schema.func"}` | UC function (grant `EXECUTE` to the agent SP) |
| `uc_connection` | `{"name": "<connection_name>"}` | External MCP server via a UC HTTP connection |
| `volume` | `{"name": "<full_volume_name>"}` | UC volume browsing |
| `app` | `{"name": "<app_name>"}` | Databricks App |
| `serving_endpoint`, `lakeview_dashboard`, `supervisor_agent`, `uc_table`, `vector_search_index`, `catalog`, `schema`, `web_search` | varies | Not verified; check `create-tool --help` |

**MCP tool:** create the UC HTTP connection with the secret from a secret scope (never inline), grant `USE CONNECTION` to the agent SP, attach as `uc_connection`. Test: `SELECT http_request(conn => 'my_mcp', method => 'POST', path => '', json => '{"jsonrpc":"2.0","method":"tools/list","id":1}')`.

```sql
CREATE CONNECTION my_mcp TYPE HTTP OPTIONS (
  host 'https://my-app.databricksapps.com', port '443', base_path '/api/mcp',
  client_id '<sp_id>', client_secret secret('<scope>', '<key>'), oauth_scope 'all-apis',
  token_endpoint 'https://<workspace>/oidc/v1/token', is_mcp_connection 'true');
GRANT USE CONNECTION ON my_mcp TO `<agent_sp>`;
```

**Descriptions drive routing**, so be specific ("Handles billing: invoices, payments, refunds", not "Billing agent").

### Examples

`guidelines` is a repeated string → `--json` only (the positional `GUIDELINES` arg doesn't accept any encoding). Examples can be added before the endpoint is ONLINE; evaluating routing needs it ONLINE.

```bash
databricks supervisor-agents create-example supervisor-agents/<id> --json '{
  "question": "What were Q4 revenue numbers?", "guidelines": ["Route to analyst Genie space"]}'
databricks supervisor-agents list-examples  supervisor-agents/<id>
databricks supervisor-agents get-example    supervisor-agents/<id>/examples/<ex_id>
databricks supervisor-agents delete-example supervisor-agents/<id>/examples/<ex_id>
```

**Troubleshooting:** wrong routing → sharper, non-overlapping descriptions + examples. Not responding / slow → check the underlying endpoints' state, logs, latency, and scaling.
