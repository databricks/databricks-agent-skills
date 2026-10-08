# Model provider services

Read this reference when creating or managing a Unity Gateway model provider service.

A model provider service is a Unity Catalog securable that stores authentication and
request configuration for an external model provider. A model service can reference it as
an external-model destination.

## Resource names

| Resource | Form |
|---|---|
| Parent schema | `schemas/<catalog>.<schema>` |
| Model provider service | `model-provider-services/<catalog>.<schema>.<service>` |
| Unity Catalog service credential | `credentials/<credential-name>` |

Create takes the parent schema and unqualified service ID as positional arguments. Get,
update, and delete take the full model-provider-service resource name.

## Resolve required inputs first

Do not construct a create payload or enumerate workspace resources until these choices are
known:

- CLI profile
- Parent catalog and schema
- Model provider service ID
- Provider type
- Provider endpoint, region, project, or organization fields required for that provider
- Authentication mode and an already-provisioned credential or secret
- Target policy: explicit upstream models and native API types, or explicit confirmation to
  allow all targets
- Whether to forward headers, query parameters, or unmanaged paths
- Optional rate limits and inference-table logging

Ask for all missing required choices together. Do not infer the service ID from the
provider, credential, or target name. Provider accounts, endpoints, app registrations,
cloud permissions, API keys, and Unity Catalog service credentials are external
prerequisites; do not provision or replace them unless the user separately requests it.

Default the three forwarding settings to false when they are not requested. Enabling them
broadens the upstream request surface, so require an explicit choice. Prefer explicit
targets; `allow_all_targets` requires explicit confirmation.

When using a Unity Catalog service credential, verify its exact name without listing every
credential:

```bash
databricks credentials get-credential "<credential-name>" \
  --profile <PROFILE>
```

## Provider configuration

Set `config.provider_type` and exactly one matching provider field. The provider type cannot
be changed after creation. Updates cannot switch between Unity Catalog service-credential
authentication and inline authentication.

| Provider | `provider_type` | Provider field and authentication |
|---|---|---|
| OpenAI | `EXTERNAL_MODEL_PROVIDER_TYPE_OPENAI` | `openai.direct`; API key, optional base URL and organization |
| Azure OpenAI | `EXTERNAL_MODEL_PROVIDER_TYPE_AZURE_OPENAI` | `azure_openai.direct`; API key, Entra service principal, or Azure UC service credential |
| Anthropic | `EXTERNAL_MODEL_PROVIDER_TYPE_ANTHROPIC` | `anthropic.direct` with API key, or `anthropic.relayed` with caller OAuth |
| Amazon Bedrock | `EXTERNAL_MODEL_PROVIDER_TYPE_AMAZON_BEDROCK` | `amazon_bedrock.direct`; region plus access keys or AWS UC service credential |
| Custom OpenAI-compatible | `EXTERNAL_MODEL_PROVIDER_TYPE_CUSTOM` | `custom.direct`; base URL and bearer token |
| Microsoft Foundry | `EXTERNAL_MODEL_PROVIDER_TYPE_MICROSOFT_FOUNDRY` | `microsoft_foundry.direct`; base URL plus API key, Entra service principal, or Azure UC service credential |
| Gemini Enterprise | `EXTERNAL_MODEL_PROVIDER_TYPE_GEMINI_ENTERPRISE` | `gemini_enterprise.direct`; project, region, and API key |

Authentication alternatives are mutually exclusive. UC service credentials are supported
only for the provider and workspace cloud combinations described above.

## Create

Inspect `databricks ai-gateway create-model-provider-service -h` before constructing the
request. This OpenAI example restricts the service to one target:

```json
{
  "comment": "Governed OpenAI access",
  "config": {
    "provider_type": "EXTERNAL_MODEL_PROVIDER_TYPE_OPENAI",
    "openai": {
      "direct": {
        "api_key": {
          "plaintext": "<secret>"
        }
      }
    },
    "allow_all_targets": false,
    "targets": [
      {
        "model": "<provider-model>",
        "native_api_types": [
          "openai/v1/chat/completions"
        ]
      }
    ]
  }
}
```

Each target requires its provider-side model identifier and at least one supported native
API type. These are provider identifiers, not Unity Catalog model resource names. Use the
exact models and API types requested by the user; do not substitute a similar model.

Before create, call `get-model-provider-service` for the exact intended resource name. If
it exists, stop and ask whether to keep it, update it, or explicitly delete and recreate it.
A different service ID using the same provider or credential is not a collision.

Do not ask the user to paste secrets into the conversation, put secrets in source-controlled
files, or pass plaintext secrets directly in shell arguments. For inline authentication,
have the user set an environment variable and create a permission-restricted temporary JSON
file. Show a redacted payload for review before execution. For example:

```bash
provider_payload_path="$(mktemp)"
trap 'rm -f "$provider_payload_path"' EXIT
chmod 600 "$provider_payload_path"
test -n "${PROVIDER_API_KEY:-}" || exit 1
jq -n '{
  comment: "Governed OpenAI access",
  config: {
    provider_type: "EXTERNAL_MODEL_PROVIDER_TYPE_OPENAI",
    openai: {direct: {api_key: {plaintext: env.PROVIDER_API_KEY}}},
    allow_all_targets: false,
    targets: [{
      model: "<provider-model>",
      native_api_types: ["openai/v1/chat/completions"]
    }]
  }
}' > "$provider_payload_path"

databricks ai-gateway create-model-provider-service \
  "schemas/<catalog>.<schema>" "<service>" \
  --json @"$provider_payload_path" \
  --profile <PROFILE>
```

Do not print the populated payload. Inline secret values are input-only and do not
round-trip on reads. Prefer a supported UC service credential over inline credentials when
the user has one available.

After create, read the exact service back and verify the non-secret persisted
configuration.

### Targets and passthrough policy

When `allow_all_targets` is false, at least one entry in `targets` is required and only
listed models are routable. When true, any upstream model is routable; target entries add
API-type metadata without restricting other models.

`forward_headers`, `forward_query_parameters`, and `forward_unmanaged_paths` each default
to false. Authentication headers are configured separately and do not require general
header forwarding. `forward_unmanaged_paths` exposes provider paths Unity Gateway does not
recognize, so enable it only when explicitly required.

### Rate limits and inference tables

`config.rate_limits` uses the same keys and renewal periods documented in
[model-services.md](model-services.md). Provider-service rate limits apply to requests sent
directly to the provider service. Requests routed through a model service use the model
service's rate limits instead.

Set `config.inference_table` to log direct provider-service traffic:

```json
{
  "parent": "schemas/<catalog>.<schema>",
  "table_name_prefix": "<prefix>"
}
```

Traffic routed through a model service is logged by that model service instead. The
inference-table parent and prefix cannot be changed after creation.

## Read and list

```bash
databricks ai-gateway get-model-provider-service \
  "model-provider-services/<catalog>.<schema>.<service>" \
  --profile <PROFILE>

databricks ai-gateway list-model-provider-services \
  --parent "schemas/<catalog>.<schema>" \
  --view FULL \
  --profile <PROFILE>
```

List results are paginated. If the response contains `next_page_token`, follow the
installed CLI help for the supported continuation mechanism rather than assuming a flag.

## Update

Read the exact service immediately before an update and use its current ETag. Put only the
changed fields in a reviewable JSON file and prefer granular masks:

```bash
databricks ai-gateway update-model-provider-service \
  "model-provider-services/<catalog>.<schema>.<service>" \
  "config.targets" \
  --json @model-provider-service-update.json \
  --etag "<etag-from-get>" \
  --profile <PROFILE>
```

Supported mask paths are:

- `comment`
- `config.provider` for the active provider-specific field; provider type remains immutable,
  and updates cannot switch between UC service-credential and inline authentication
- `config.allow_all_targets`
- `config.targets`
- `config.forward_headers`
- `config.forward_query_parameters`
- `config.forward_unmanaged_paths`
- `config.rate_limits`
- `config.inference_table`
- `config` to replace the entire configuration

The mask for a provider-specific value is always `config.provider`, not a path such as
`config.openai`. Wildcards are unsupported. A full `config` replacement must include every
required field and clears optional fields that are omitted. Inline secret values omitted
from read responses must be supplied again when the chosen update requires them. Read the
service back and verify the intended non-secret fields after updating.

## Delete

Deletion is irreversible and can break model services that reference this provider
service. Read the exact service, identify known dependents when practical, show the target,
and obtain confirmation immediately before running:

```bash
databricks ai-gateway delete-model-provider-service \
  "model-provider-services/<catalog>.<schema>.<service>" \
  --etag "<etag-from-get>" \
  --profile <PROFILE>
```

After deletion, call `get-model-provider-service` for the same full name and verify it is
not found.

## Required privileges

- Create: schema owner, or `CREATE SERVICE` and `USE SCHEMA` on the schema plus
  `USE CATALOG` on the catalog.
- Inline credentials additionally require `CREATE CONNECTION` on the parent schema.
- UC service-credential authentication requires `ACCESS` on the referenced credential.
- Read/list: `USE CATALOG`, `USE SCHEMA`, and access through ownership or `EXECUTE`,
  `READ METADATA`, or `MANAGE`.
- Update/delete: owner or `MANAGE`, plus `USE CATALOG` and `USE SCHEMA`.
