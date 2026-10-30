# Tracing on Databricks (Unity Catalog storage)

Use UC Delta tables by default. Tracking URI plus experiment alone means legacy workspace storage; use legacy only when explicitly requested. Python UC setup requires [MLflow >=3.14](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/trace-unity-catalog). Inspect installed SDKs, existing application configuration and deployment manifests before editing.

## Authenticate and select the destination

- Check auth: `databricks current-user me --profile <name>`; confirm `mlflow.get_tracking_uri()`.
- Expired auth: `databricks auth login --profile <name>`. Never print/save auth-token output.

## Select a SQL warehouse automatically

Reuse a configured warehouse; otherwise discover warehouses through the authenticated workspace and select an accessible candidate, preferring one already running. Verify access during setup; try another discovered candidate if unusable. Do not reject a warehouse merely because of its name/owner or ask the user to choose among usable ones. Ask for a warehouse only when no usable candidate can be discovered. This setup selection does not authorize cycling warehouses during bounded readback.

## Choose the schema before provisioning

Reuse a destination already explicitly supplied/authorized, including an explicit request to reuse project configuration. Otherwise ask whether to use an existing schema or create one; discovered config is a candidate, not authorization to select an arbitrary accessible schema.

- Existing: obtain/confirm `catalog.schema` and verify it exists.
- New: obtain catalog/schema, explain schema and trace-table creation, and establish authorization (reuse existing authorization). Check create-schema permission in that catalog; do not switch catalogs as a fallback.
- Confirm `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE` and warehouse access before binding. On failure report the chosen destination/operation and required access or explicit alternative, without falling back to another schema or legacy storage.

## Configure Python tracing

Inspect `experiment.trace_location` before reusing an experiment. A UC binding is permanent: reuse a matching location, bind an unbound experiment, or resolve a conflicting location with the user/new experiment. Binding changes new writes; it does not migrate old legacy traces.

```python
import os
import mlflow
from mlflow.entities.trace_location import UnityCatalog

mlflow.set_tracking_uri("databricks://<PROFILE>")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<WAREHOUSE_ID>"
mlflow.set_experiment(
    experiment_name="/Users/<email>/<experiment-name>",
    trace_location=UnityCatalog(catalog_name="<catalog>", schema_name="<schema>"),
)
```

Reuse an existing numeric experiment ID when appropriate; Databricks experiment names must be absolute workspace paths such as `/Users/<email>/name` or `/Shared/name`. `UnityCatalog` provisions trace tables, not the schema-selection decision. Omit optional `table_prefix` to default to experiment ID; supply it only for an intended custom prefix. Tables use `<prefix>_otel_spans`, `_otel_logs`, `_otel_metrics`, `_otel_annotations`.

Explicit creation is also supported via `mlflow.create_experiment(name=..., trace_location=...)`, then `mlflow.set_experiment(experiment_id=...)`. If the required API is unavailable, report/resolve the version prerequisite rather than omitting UC configuration.

## TypeScript

Use `@mlflow/core >=0.4.0`, which supports `init().traceLocation`. Older versions cannot write to UC trace tables; upgrade or report the limitation rather than claiming UC storage from `trackingUri`/`experimentId` alone.

Provision and link the location once with Python, then use its exact prefix:

```typescript
import * as mlflow from "@mlflow/core";
mlflow.init({
  trackingUri: "databricks://<PROFILE>", experimentId: "<NUMERIC_ID>",
  traceLocation: {
    catalogName: "<catalog>", schemaName: "<schema>", tablePrefix: "<EXACT_PREFIX>",
  },
});
```

TypeScript cannot provision the location or default the prefix: all three fields are required in supporting versions.

## Trace deployed agents

- Configure deployments with the selected tracking URI and numeric experiment ID.
- **Databricks Apps:** grant the service identity access to the experiment, UC schema and warehouse; configure environment/resources without embedding personal tokens. Initialize tracing before the handler's first span.
- **Model Serving:** instrument `predict`/the agent entry point before deployment and verify the endpoint identity can export. A traced client call does not prove internal endpoint spans exist.
- **External OTel:** use the documented ingestion endpoint, auth and resource attributes for the installed deployment, not an arbitrary workspace URL. Preserve W3C context; attribute conventions may differ from MLflow's.

## Verification

Follow [single-run bounded readback](../guide.md#verification). Inspect experiment metadata to confirm the actual `UnityCatalog` catalog/schema/prefix matches the selected location, then reuse the retrieved application trace. Presence in the UI alone does not prove UC storage. For deployed work, execute under the deployed identity and inspect root/child I/O, timing and available token fields.

UC `get_trace()` also consumes warehouse capacity. If readback times out or returns auth/permission/warehouse errors or `RESOURCE_EXHAUSTED`/429, stop with the operation, error, failing identity and saved trace ID. Do not switch warehouse, direct SQL, raw REST or legacy storage to force verification. If no ID was saved, the one fallback search needs run-time bounds and `max_results=1`.

## Link to the verified trace

```text
https://<workspace-host>/ml/experiments/<experiment-id>/traces/<trace-id>
```

Use the host from authenticated configuration; `databricks://<profile>` is not a browser URL. Use the application's numeric experiment ID, not its name or table/schema; UC `trace.info.experiment_id` may be `None`. Resolve missing host/experiment identity instead of guessing.

For `trace:/catalog.schema/<hex-id>`, use only the final hex component in the browser path while retaining the **full qualified ID for SDK calls**. Keep `tr-` on legacy IDs. Append `?o=<workspace-id>` only if already known from the workspace URL. Do not substitute OSS `#/experiments/...`, run or REST URLs. Label links unverified when readback failed.

Exact platform docs: [UC trace storage](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/trace-unity-catalog), [trace URL FAQ](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/faq). Check installed APIs; these links supplement the destination-selection and stopping rules above.
