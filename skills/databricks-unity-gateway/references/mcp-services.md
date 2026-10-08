# MCP services

Read this reference when creating or managing a Unity Gateway MCP service.

An MCP service is a Unity Catalog securable backed by a Unity Catalog HTTP connection. It
governs discovery and invocation of tools exposed by the external MCP server.

## Resource names

Use the exact resource-name forms expected by the CLI:

| Resource | Form |
|---|---|
| Parent schema | `schemas/<catalog>.<schema>` |
| MCP service | `mcp-services/<catalog>.<schema>.<service>` |
| Source connection | `connections/<catalog>.<schema>.<connection>` |

Create takes the parent schema and unqualified service ID as positional arguments. Get,
update, and delete take the full MCP-service resource name.

## Resolve required inputs first

Do not construct a create payload or enumerate workspace resources until these choices are
known:

- CLI profile
- Parent catalog and schema
- MCP service ID
- Exact source connection
- Tool exposure: exact or prefix selectors, or explicit confirmation to expose every tool
- Optional rate limits

Ask for all missing required choices together. If only some are answered, ask for the
remainder rather than inferring them. Never infer the service ID from the connection name.
Omitting `include_tool_selectors` exposes every tool, so do not omit it without explicit user
confirmation.

Verify the exact source connection without broadly listing connections:

```bash
databricks connections get "<catalog>.<schema>.<connection>" \
  --profile <PROFILE>
```

## Create

Inspect `databricks ai-gateway create-mcp-service -h` before constructing the request. Put
the configuration in a JSON file so it can be reviewed before submission.

```json
{
  "comment": "Governed external MCP server",
  "config": {
    "source_connection": {
      "name": "connections/<catalog>.<schema>.<connection>"
    },
    "include_tool_selectors": [
      "read_*"
    ]
  }
}
```

```bash
databricks ai-gateway create-mcp-service \
  "schemas/<catalog>.<schema>" "<service>" \
  --json @mcp-service.json \
  --profile <PROFILE>
```

`config` and `config.source_connection.name` are required. Do not include
`source_connection.options`; it is output-only.

Before create, call `get-mcp-service` for the exact intended resource name. If it already
exists, do not create a duplicate or report creation as completed. Show the existing
resource and ask whether to keep it, update it, or explicitly delete and recreate it.
Deletion requires separate confirmation. A service backed by the same connection but using
a different service ID is not a collision.

After create, read the exact service back and verify its persisted configuration.

### Tool selectors

`config.include_tool_selectors` accepts exact tool names and prefix patterns such as
`read_*`. Exclusion patterns are unsupported. An omitted or empty list exposes all tools.
Use no more than 1,024 selectors, each no more than 256 characters.

Prefer the narrowest selectors that satisfy the request. End users generally need
`EXECUTE` on the MCP service, not `USE CONNECTION`; granting direct connection access can
bypass the service's governance.

### Rate limits

`config.rate_limits` is an array. Each entry requires `key` and `renewal_period`.
`requests` and `tokens` are independent optional limits. A limit of `0` denies requests;
omission means no limit of that kind.

```json
{
  "key": "RATE_LIMIT_KEY_USER_GROUP",
  "principal": "<group-name>",
  "renewal_period": "RATE_LIMIT_RENEWAL_PERIOD_MINUTE",
  "requests": 60,
  "tokens": 100000
}
```

Supported keys are `RATE_LIMIT_KEY_USER`, `RATE_LIMIT_KEY_USER_GROUP`,
`RATE_LIMIT_KEY_SERVICE_PRINCIPAL`, `RATE_LIMIT_KEY_SERVICE`, and
`RATE_LIMIT_KEY_USER_DEFAULT`. Set `principal` only for a specific user, group, or service
principal. Renewal periods are `RATE_LIMIT_RENEWAL_PERIOD_MINUTE` and
`RATE_LIMIT_RENEWAL_PERIOD_HOUR`.

## Read and list

```bash
databricks ai-gateway get-mcp-service \
  "mcp-services/<catalog>.<schema>.<service>" \
  --profile <PROFILE>

databricks ai-gateway list-mcp-services \
  --parent "schemas/<catalog>.<schema>" \
  --view FULL \
  --profile <PROFILE>
```

List results are paginated. If the response contains `next_page_token`, follow the
installed CLI help for the supported continuation mechanism rather than assuming a flag.

## Update

Read the exact service immediately before an update and use its current ETag. Put changed
fields in a reviewable JSON file and prefer granular masks so omitted siblings are not
cleared:

```bash
databricks ai-gateway update-mcp-service \
  "mcp-services/<catalog>.<schema>.<service>" \
  "config.include_tool_selectors" \
  --json @mcp-service-update.json \
  --etag "<etag-from-get>" \
  --profile <PROFILE>
```

Supported mask paths are:

- `comment`
- `config.source_connection.name`
- `config.include_tool_selectors`
- `config.rate_limits`
- `config` to replace the entire configuration

Wildcards are unsupported. A `config` replacement must include every required field and
clears optional fields that are omitted. Changing the connection requires `USE CONNECTION`
on the new connection. Read the service back after update and verify the intended fields.

## Delete

Deletion is irreversible. Read the exact service, show the target, and obtain confirmation
immediately before running:

```bash
databricks ai-gateway delete-mcp-service \
  "mcp-services/<catalog>.<schema>.<service>" \
  --etag "<etag-from-get>" \
  --profile <PROFILE>
```

After deletion, call `get-mcp-service` for the same full name and verify it is not found.

## Required privileges

- Create: schema owner, or `CREATE SERVICE` and `USE SCHEMA` on the schema plus
  `USE CATALOG` on the catalog; also `USE CONNECTION` on the source connection.
- Read/list: `USE CATALOG`, `USE SCHEMA`, and access through ownership or `EXECUTE`,
  `READ METADATA`, or `MANAGE`.
- Update/delete: owner or `MANAGE`, plus `USE CATALOG` and `USE SCHEMA`.

SQL DDL is not supported for MCP services.
