# Model services

Read this reference when creating or managing a Unity Gateway model service.

A model service is a Unity Catalog securable in a schema that routes inference requests to one or more destinations, with configurable fallbacks, rate limits, and inference-table logging. Databricks-hosted models already have model services in `system.ai`; authorized users can configure their rate limits and logging without creating another service. Create your own for separately governed configuration, custom routing and fallbacks, or external-model or provisioned-throughput destinations.

- [Model services](https://docs.databricks.com/aws/en/ai-gateway/model-services)
- [Inference-table requirements](https://docs.databricks.com/aws/en/ai-gateway/inference-tables)
- [Create a model service](https://docs.databricks.com/aws/en/ai-gateway/create-model-services)

## Resource names

Use the exact resource-name forms expected by the CLI:

| Resource | Form |
|---|---|
| Parent schema | `schemas/<catalog>.<schema>` |
| Model service | `model-services/<catalog>.<schema>.<service>` |
| Unity Catalog model | `models/<catalog>.<schema>.<model>` |
| Model provider service | `model-provider-services/<catalog>.<schema>.<service>` |
| Model Serving endpoint | `serving-endpoints/<endpoint-name>` |

The create command takes the parent schema and the unqualified service ID as positional
arguments. Get, update, and delete take the full model-service resource name.

## Resolve required inputs first

Do not construct a create payload or enumerate workspace resources until these choices are
known:

- CLI profile
- Parent catalog and schema for the new model service
- Model service ID
- Destination type and exact backing model, endpoint, or model provider service
- When inference-table logging is requested: its parent catalog/schema and optional table
  prefix

Ask for all missing required choices together. If the user answers only some of them, ask
for the remainder instead of choosing a catalog/schema or listing unrelated services to
infer one. Multiple destinations, fallback routing, rate limits, and inference-table
logging are optional; if they were not requested, state that they will be omitted.

Resolve an informal model name to an exact backing resource only after the profile is
known. Do not substitute a similarly named model.

## Create

Inspect `databricks ai-gateway create-model-service -h` before constructing the request.
Put the configuration in a JSON file so it can be reviewed before it is submitted.

Minimal pay-per-token destination:

```json
{
  "comment": "Governed access to a foundation model",
  "config": {
    "routing": {
      "destinations": [
        {
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": {
            "model": "models/<catalog>.<schema>.<model>"
          }
        }
      ]
    }
  }
}
```

```bash
databricks ai-gateway create-model-service \
  "schemas/<catalog>.<schema>" "<service>" \
  --json @model-service.json \
  --profile <PROFILE>
```

Do not put the service resource name in the payload. The service name is derived from the
parent and service ID.

Before create, call `get-model-service` for the exact intended resource name. If it already
exists, do not create a duplicate and do not report the create request as completed. Show
the existing resource and ask whether the user wants to keep it, update it, or explicitly
delete and recreate it. Deletion requires separate confirmation.

Current configuration proves only the resource's present state. Do not claim that an
existing inference table or other setting was configured at creation time without
historical evidence.

### Destination types

Each destination requires `name`, `destination_type`, and exactly one matching
type-specific configuration.

| Destination | `destination_type` | Configuration |
|---|---|---|
| Databricks pay-per-token model | `DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL` | `"pay_per_token_config": {"model": "models/<catalog>.<schema>.<model>"}` |
| Provisioned-throughput model | `DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL` | `"provisioned_throughput_config": {"model_serving_endpoint": "serving-endpoints/<endpoint-name>"}` |
| External model | `DESTINATION_TYPE_EXTERNAL_FOUNDATION_MODEL` | `"external_model_config": {"model_provider_service": "model-provider-services/<catalog>.<schema>.<service>", "target": {"model": "<provider-model>", "native_api_types": ["<api-type>"]}}` |

For multiple primary destinations, set `traffic_percentage` on each and make the values
sum to 100. A single destination receives all traffic without this field. At most 10
primary destinations are allowed.

### Fallback routing

Put fallback destinations in `config.routing.fallback.destinations`. They use the same
destination shape as primary destinations, but are tried in array order and do not use
`traffic_percentage`.

```json
{
  "config": {
    "routing": {
      "destinations": [
        {
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": {
            "model": "models/<catalog>.<schema>.<primary-model>"
          }
        }
      ],
      "fallback": {
        "destinations": [
          {
            "name": "fallback",
            "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
            "pay_per_token_config": {
              "model": "models/<catalog>.<schema>.<fallback-model>"
            }
          }
        ]
      }
    }
  }
}
```

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

### Inference-table logging

Set `config.inference_table` to enable payload logging:

```json
{
  "parent": "schemas/<catalog>.<schema>",
  "table_name_prefix": "<prefix>"
}
```

Unity Gateway appends `_payload` to the prefix. The parent and prefix cannot be changed
after the inference table is created. The creator needs `CREATE TABLE` on the target
schema.

## Read and list

```bash
databricks ai-gateway get-model-service \
  "model-services/<catalog>.<schema>.<service>" \
  --profile <PROFILE>

databricks ai-gateway list-model-services \
  --parent "schemas/<catalog>.<schema>" \
  --view FULL \
  --profile <PROFILE>
```

List results are paginated. If the response contains `next_page_token`, follow the
installed CLI help for the supported continuation mechanism rather than assuming a flag.

## Update

Updates require the full resource name and an update mask. Prefer granular masks so an
omitted sibling field is not cleared:

```bash
databricks ai-gateway update-model-service \
  "model-services/<catalog>.<schema>.<service>" \
  "config.rate_limits" \
  --json @model-service-update.json \
  --etag "<etag-from-get>" \
  --profile <PROFILE>
```

Supported mask paths are:

- `comment`
- `config.routing.destinations`
- `config.routing.fallback.destinations`
- `config.rate_limits`
- `config.inference_table`
- `config` to replace the entire configuration

Do not use intermediate paths such as `config.routing` or wildcard paths. A `config`
replacement must include every required field and clears optional fields that are omitted.
Use the most recent `etag` for optimistic concurrency when multiple actors may update the
service.

## Delete

Deletion is irreversible. Resolve the full resource name with `get-model-service`, show the
target to the user, and obtain confirmation before running:

```bash
databricks ai-gateway delete-model-service \
  "model-services/<catalog>.<schema>.<service>" \
  --etag "<etag-from-get>" \
  --profile <PROFILE>
```

## Required privileges

- Create: schema owner, or `CREATE SERVICE` and `USE SCHEMA` on the schema plus
  `USE CATALOG` on the catalog.
- Read/list: `USE CATALOG`, `USE SCHEMA`, and access through ownership or `EXECUTE`,
  `READ METADATA`, or `MANAGE`.
- Update/delete: owner or `MANAGE`, plus `USE CATALOG` and `USE SCHEMA`.
- Destinations: `USE CATALOG`, `USE SCHEMA`, and `EXECUTE` on each referenced model or
  model provider service. Provisioned throughput requires `CAN_MANAGE` on the backing
  Model Serving endpoint; when destinations are updated, the service owner also needs
  `CAN_QUERY` on that endpoint.

Model services use definer's privileges: callers need `EXECUTE` on the model service, while
the service owner must retain access to its destinations.
