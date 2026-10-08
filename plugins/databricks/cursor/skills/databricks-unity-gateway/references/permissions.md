# Permissions

Read this reference before inspecting or changing access to Unity Gateway securables.
Permission operations use `databricks grants` and require an explicit CLI profile.

## Query access

A caller needs all three privileges:

| Securable | Required privileges |
|---|---|
| Parent catalog | `USE CATALOG` |
| Parent schema | `USE SCHEMA` |
| Model service, model provider service, or MCP service | `EXECUTE` |

The caller also needs the workspace entitlement required to query: **Workspace access**, or
**Consumer access** when the account has enabled Consumer access to Unity Gateway.

Callers do not need access to a model provider service's stored provider credential or a
MCP service's source connection. Granting access to those dependencies can bypass the
service's governance boundary.

## Model Serving `CAN_QUERY` does not grant Unity Gateway access

Serving-endpoint ACLs (`CAN_QUERY`, `CAN_MANAGE`) and Unity Catalog privileges are separate
governance planes. A principal with `CAN_QUERY` on a Model Serving endpoint has no access to
a Unity Gateway model service, even one that replaced that endpoint. The symptom is
`PERMISSION_DENIED` when a workload that previously queried a serving endpoint now calls a
three-part model name (`<catalog>.<schema>.<service>`).

Granting UC privileges alone does not fix it; the client must also move off the serving
endpoint. Both steps are required:

1. **Grant UC privileges** on the model service to the failing principal -- for an app or
   job, its service principal (application/client ID), not the deploying user: `EXECUTE` on
   the service plus `USE CATALOG` and `USE SCHEMA` on its parents (see
   [Query access](#query-access)).
2. **Repoint the client** from `/serving-endpoints/...` to a Unity Gateway path with the
   three-part name as `model` (see [Query services](querying.md)).

See [Migration](model-serving-migration.md) when the endpoint was replaced during a
migration, or when **Enforce Unity Gateway** blocks legacy `databricks-*` calls.

## Inspect access first

Resolve the profile, exact principal, service type, and three-part service name before
changing permissions. Inspect effective permissions because catalog and schema grants are
inherited:

```bash
databricks grants get-effective model_service \
  "<catalog>.<schema>.<service>" \
  --principal "<principal>" \
  --profile <PROFILE>
```

Use `model_provider_service` or `mcp_service` for the other Unity Gateway securables. Use
`databricks grants get` when only direct, non-inherited grants are needed.

## Grant query access

Use reviewable JSON payloads. Grant only missing privileges; do not replace unrelated
grants or grant `MANAGE` when the caller only needs to query.

Before granting to a group, read [Account access](account-access.md). A group principal
must be an account-level group; a workspace-local group cannot receive UC grants.

```json
{
  "changes": [
    {
      "principal": "<principal>",
      "add": ["EXECUTE"]
    }
  ]
}
```

```bash
databricks grants update model_service \
  "<catalog>.<schema>.<service>" \
  --json @service-grant.json \
  --profile <PROFILE>
```

If the principal lacks parent access, grant it separately:

```bash
databricks grants update catalog "<catalog>" \
  --json '{"changes":[{"principal":"<principal>","add":["USE_CATALOG"]}]}' \
  --profile <PROFILE>

databricks grants update schema "<catalog>.<schema>" \
  --json '{"changes":[{"principal":"<principal>","add":["USE_SCHEMA"]}]}' \
  --profile <PROFILE>
```

Replace `model_service` with `model_provider_service` or `mcp_service` as appropriate.
Verify the principal's effective permissions after the update. Privilege changes can take a
few minutes to propagate to query requests.

## Revoke access

Revocation is a mutation and can interrupt workloads. Show the exact principal, securable,
and privilege, then obtain confirmation immediately before using `remove`:

```json
{
  "changes": [
    {
      "principal": "<principal>",
      "remove": ["EXECUTE"]
    }
  ]
}
```

Do not revoke shared `USE CATALOG` or `USE SCHEMA` privileges merely to remove access to one
service. Revoke `EXECUTE` on that service and verify effective permissions afterward.

## Creation and management access

Creating a service requires `USE CATALOG`, `USE SCHEMA`, and `CREATE SERVICE` on its parent.
Additional requirements depend on its configuration:

- Model service: `EXECUTE` on each model destination. A model-provider destination also
  requires `USE CATALOG`, `USE SCHEMA`, and `EXECUTE` on that provider service.
- Inference table: `USE CATALOG`, `USE SCHEMA`, and `CREATE TABLE` on its target schema.
- Model provider service with inline credentials: `CREATE CONNECTION` on its parent schema.
- Model provider service using a UC service credential: its owner must retain `ACCESS` on
  the credential. When backed by a UC secret, its owner must retain `READ SECRET`.
- MCP service: `USE CONNECTION` on its source connection.

Owners or principals with `MANAGE` can modify grants and service configuration. Grant
`MANAGE` only when the principal is intended to administer the service. A provider-service
caller needs no privilege on its underlying credential; an MCP-service caller needs no
`USE CONNECTION` on its source connection.
