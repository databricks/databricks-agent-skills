---
name: databricks-unity-gateway
description: >-
  Use when querying or calling pay-per-token foundation models, or when
  creating, updating, listing, or querying Unity Gateway (also called Unity AI
  Gateway) services, including model provider services, MCP services, system.ai
  services, and three-part Unity Catalog service names (catalog.schema.service).
  Also use for managing spend budgets and usage alerts on Unity Gateway, and for
  migrating from legacy AI Gateway. Also use when a workload with Model Serving
  endpoint permissions (for example CAN_QUERY) gets PERMISSION_DENIED querying a
  three-part model name, since serving-endpoint access does not grant access to a
  Unity Gateway service. Not for configuring legacy AI Gateway on Model Serving
  endpoints; use databricks-model-serving for that.
compatibility: Requires databricks CLI (>= v1.11.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Unity Gateway

Use the parent `databricks-core` skill for CLI authentication and profile selection.

Unity Gateway provides Unity Catalog securables for governed access to AI services. The CLI
command group keeps the earlier product name: `databricks ai-gateway --help`.

## Choose the Correct Gateway

| Request | Use |
|---|---|
| Unity Gateway model service, MCP service, or model provider service | This skill and `databricks ai-gateway` |
| AI Gateway configuration on a Model Serving endpoint, including `put-ai-gateway` | `databricks-model-serving` and `databricks serving-endpoints` |
| Lakeflow Connect ingestion gateway | `databricks-lakeflow-connect` |

Treat **Unity AI Gateway** as an earlier name for **Unity Gateway** when the resource is a
Unity Catalog securable. Do not translate legacy Model Serving AI Gateway resources into
Unity Gateway resources unless the user explicitly requests a migration.

## CLI Workflow

Use the Databricks CLI for resource lifecycle and permission management. Do not substitute
direct REST calls or a Databricks SDK for those operations. Python clients are supported
for querying model and model provider services; read [Query services](references/querying.md).

An explicit request for **Unity Gateway**, **Unity AI Gateway**, or
`databricks ai-gateway` belongs to this skill. Do not switch to
`databricks-model-serving` merely because the request involves a model service or a
workspace. Use that skill only for a legacy per-endpoint AI Gateway operation or when a
provisioned-throughput destination requires Model Serving endpoint details.

1. Verify the CLI meets the minimum version:

   ```bash
   databricks --version
   ```

2. Inspect the command and the relevant operation before constructing a payload:

   ```bash
   databricks ai-gateway --help
   databricks ai-gateway <operation> --help
   ```

3. Pass create and update configuration through `--json`. Use an explicit profile when
   profile-based authentication is required:

   ```bash
   databricks ai-gateway <operation> --json @payload.json --profile <PROFILE>
   ```

Do not invent JSON fields from similarly named legacy APIs. Build the payload from the
installed CLI help and the Unity Gateway documentation for the selected service type.

## Service Types

| Service type | CLI operations |
|---|---|
| Model service | `create-model-service`, `get-model-service`, `list-model-services`, `update-model-service`, `delete-model-service`; read [Model services](references/model-services.md) |
| MCP service | `create-mcp-service`, `get-mcp-service`, `list-mcp-services`, `update-mcp-service`, `delete-mcp-service`; read [MCP services](references/mcp-services.md) |
| Model provider service | `create-model-provider-service`, `get-model-provider-service`, `list-model-provider-services`, `update-model-provider-service`, `delete-model-provider-service`; read [Model provider services](references/model-provider-services.md) |

## Querying and permissions

- Before writing Python that invokes a model or model provider service, read [references/querying.md](references/querying.md).
- Before checking, granting, or revoking Unity Gateway access, read [references/permissions.md](references/permissions.md).
- Before any model-service operation, read [references/model-services.md](references/model-services.md). It contains the current resource-name conventions, JSON payload fields, required-input gate, and lifecycle commands.
- Before any MCP-service operation, read [references/mcp-services.md](references/mcp-services.md) for the equivalent MCP-specific contract.
- Before any model-provider-service operation, read [references/model-provider-services.md](references/model-provider-services.md).
- Before setting up a spend budget or spend alert on Unity Gateway usage, read [references/budgets.md](references/budgets.md).
- Before any account-scoped operation (account groups as grant principals, account budgets), read [references/account-access.md](references/account-access.md).

Do not fetch public documentation for fields already covered by these references. Consult the
authoritative documentation only when a required field is absent from the reference or the
user explicitly asks for the latest documentation. Do not assign a Beta or preview status
unless the installed CLI help or current documentation explicitly does so.

## Migration from Model Serving to Unity Gateway

When migrating from workspace-scoped Model Serving endpoints to Unity Catalog-scoped Unity Gateway services, read [references/model-serving-migration.md](references/model-serving-migration.md).

## Authoritative Documentation

- [Unity Gateway overview](https://docs.databricks.com/aws/en/ai-gateway/)
- [Unity Gateway release notes](https://docs.databricks.com/aws/en/release-notes/unity-gateway/)
- [Unity Gateway developer documentation](https://developers.databricks.com/docs/agents/ai-gateway)
- [Model service API reference](https://docs.databricks.com/api/ai-gateway/v1/model-service)
- [MCP service API reference](https://docs.databricks.com/api/ai-gateway/v1/mcp-service)
- [Model provider service API reference](https://docs.databricks.com/api/ai-gateway/v1/model-provider-service)
- [Query model services](https://docs.databricks.com/aws/en/ai-gateway/query-model-services)
- [Open Responses specification](https://www.openresponses.org/specification)
- [Open Responses provider behavior on Databricks](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-open-responses-models)
- [Query model provider services](https://docs.databricks.com/aws/en/ai-gateway/query-model-provider-services)
- [Model service requirements and grants](https://docs.databricks.com/aws/en/ai-gateway/create-model-services)
- [Model provider service governance](https://docs.databricks.com/aws/en/ai-gateway/govern-model-provider-services)
- [Routing and fallbacks](https://docs.databricks.com/aws/en/ai-gateway/configure-traffic-splitting)
- [Rate limits](https://docs.databricks.com/aws/en/ai-gateway/rate-limits)
- [Register an external MCP server](https://docs.databricks.com/aws/en/ai-gateway/register-mcp-service)
