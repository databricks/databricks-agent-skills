# Migration

Use this reference to migrate workspace-scoped Model Serving and legacy AI Gateway endpoints to Unity Gateway. It adds tested commands and gaps to the public [Migrate to Unity Gateway](https://docs.databricks.com/aws/en/ai-gateway/migrate-to-unity-gateway) guide. Use `databricks-model-serving` to inspect the legacy endpoint.

| Legacy endpoint | Target |
|---|---|
| Pay-per-token `databricks-*` | `system.ai.<model>`, or a model service with a pay-per-token destination |
| Provisioned throughput | Keep the endpoint. Create a model service with a provisioned-throughput destination; see [Model services](model-services.md) |
| External model | Model provider service; see [Model provider services](model-provider-services.md) |

- Legacy settings do not move. Re-create permissions, rate limits, policies, inference logging, and routing.
- Clients need a PAT with the `ai-gateway` scope. The legacy regional `*.ai-gateway.*` host returns `403: required scopes: all-apis` for that PAT.
- Phased migration: set a legacy endpoint rate limit to `0` to stop its traffic.
- Do not state retirement dates unless they are in current public release notes.

## End-to-end example

Tested migration of pay-per-token endpoint `<legacy-endpoint>` to model service `<catalog>.<schema>.<service>`.

1. **Create the model service.** The model name is not the endpoint name (`databricks-gpt-oss-20b` serves `system.ai.gpt-oss-20b`). Get it:

   ```bash
   databricks serving-endpoints get <legacy-endpoint> --profile <PROFILE> -o json \
     | jq -r '.config.served_entities[0].foundation_model.name'
   ```

   Create the service with a pay-per-token destination `models/system.ai.<model>`; see [Model services](model-services.md).

2. **Grant access.** Grant callers `EXECUTE` on the service plus `USE CATALOG` and `USE SCHEMA`; see [Permissions](permissions.md).

3. **Send test traffic.** Send the same request to both paths and compare:

   ```python
   legacy = OpenAI(api_key=token, base_url=f"{host}/serving-endpoints")
   legacy.chat.completions.create(model="<legacy-endpoint>", messages=messages)

   gateway = OpenAI(api_key=token, base_url=f"{host}/ai-gateway/mlflow/v1")
   gateway.chat.completions.create(model="<catalog>.<schema>.<service>", messages=messages)
   ```

4. **Move clients.** Change `base_url` and `model` as in step 3. Change `ai_query('<legacy-endpoint>', ...)` to `ai_query('system.ai.<model>', ...)` -- `ai_query` is `system.ai`-only and usage-tracking-only (see [Query services](querying.md#sql-ai_query)). Record the cutover time in UTC.

5. **Confirm legacy traffic is zero.** Query `system.serving.endpoint_usage` (account admin required). It records legacy REST and `ai_query` calls only. Data can be 15 to 30 minutes late; make sure `max(request_time)` is later than the check window before you trust zero rows.

   ```sql
   SELECT u.requester, count(*) AS requests, max(u.request_time) AS last_request
   FROM system.serving.endpoint_usage u
   WHERE u.served_entity_id IN (
       SELECT served_entity_id FROM system.serving.served_entities
       WHERE endpoint_name = '<legacy-endpoint>')
     AND u.request_time >= '<cutover-utc>'
   GROUP BY ALL
   ORDER BY requests DESC;
   ```

   - `databricks-*` endpoints are shared. Filter by `requester` to check only the migrated clients.
   - Do not use `system.ai_gateway.usage` for this check. It does not record legacy REST calls. Use it to find `ai_query` callers (`invocation_metadata.source = 'AI_QUERY'`) and model-service traffic (`service_name`).
   - `databricks serving-endpoints export-metrics` fails for pay-per-token endpoints.

6. **Disable legacy paths.** After step 5 returns zero rows, a workspace admin turns on **Enforce Unity Gateway** in **Settings > Advanced**. The setting is per workspace, on by default in new workspaces, and has no public CLI key. After enforcement, `databricks-*` pay-per-token calls return `PERMISSION_DENIED: Querying pay-per-token foundation model endpoint '<name>' is disabled for this workspace. Please use Unity Gateway.` For other effects (AI Search, `ai_query`, Databricks Apps), read "Step 2: Enable Enforce Unity Gateway" in the public guide.
