# External Locations & Storage Credentials

How Unity Catalog governs access to **cloud storage**: storage credentials (the cloud
identity UC assumes) and external locations (a credential bound to a path). External
tables, external volumes, and external lineage all build on these two objects.

## The Two Objects

| Object | What it is | Backed by |
|--------|------------|-----------|
| **Storage credential** | A UC object wrapping a cloud identity (AWS IAM role, Azure managed identity / service principal, GCP service account) | The cloud IAM principal |
| **External location** | A path (`s3://…`, `abfss://…`, `gs://…`) + the storage credential allowed to access it | One storage credential |

Order of creation is always: **storage credential → external location → external table/volume**.

> **Not Iceberg REST Catalog credential vending.** UC storage credentials authorize
> *Databricks itself* to reach your cloud storage. They are **distinct** from the Iceberg
> REST Catalog (IRC) credential **vending** that hands short-lived credentials to *external
> engines* (Spark/Trino/Snowflake) — that is covered by **databricks-iceberg**, not here.

## Create a Storage Credential

### SQL

```sql
-- AWS (IAM role)
CREATE STORAGE CREDENTIAL my_s3_cred
  WITH AWS_IAM_ROLE 'arn:aws:iam::123456789012:role/my-uc-role'
  COMMENT 'Credential for the analytics S3 bucket';

-- Azure (managed identity backed by a Databricks Access Connector).
-- The value is the Access Connector's Azure resource ID — the SAME identity the
-- SDK example below passes as access_connector_id, not a bare managed-identity name.
CREATE STORAGE CREDENTIAL my_adls_cred
  WITH AZURE_MANAGED_IDENTITY
  '/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Databricks/accessConnectors/<connector>'
  COMMENT 'Credential for ADLS Gen2';

-- GCP (service account)
CREATE STORAGE CREDENTIAL my_gcs_cred
  WITH GCP_SERVICE_ACCOUNT 'uc-sa@my-project.iam.gserviceaccount.com';
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    AwsIamRoleRequest,
    AzureManagedIdentityRequest,
)

w = WorkspaceClient()

# AWS IAM role
w.storage_credentials.create(
    name="my_s3_cred",
    aws_iam_role=AwsIamRoleRequest(
        role_arn="arn:aws:iam::123456789012:role/my-uc-role",
    ),
    comment="Credential for the analytics S3 bucket",
)

# Azure managed identity (via Databricks access connector)
w.storage_credentials.create(
    name="my_adls_cred",
    azure_managed_identity=AzureManagedIdentityRequest(
        access_connector_id="/subscriptions/.../accessConnectors/my-connector",
    ),
)
```

## Create an External Location

### SQL

```sql
CREATE EXTERNAL LOCATION my_s3_location
  URL 's3://my-bucket/analytics'
  WITH (CREDENTIAL my_s3_cred)
  COMMENT 'Analytics landing zone';

-- Inspect
DESCRIBE EXTERNAL LOCATION my_s3_location;
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

w.external_locations.create(
    name="my_s3_location",
    url="s3://my-bucket/analytics",
    credential_name="my_s3_cred",
    comment="Analytics landing zone",
)
```

## Validate a Credential / Location

Validation confirms the cloud identity can actually read/write/list the path **before** you
depend on it — far easier to debug than a failed table create later.

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Validate that a credential can access a specific URL
result = w.storage_credentials.validate(
    storage_credential_name="my_s3_cred",
    url="s3://my-bucket/analytics",
)
print("Overall:", result.is_dir, result.results)

# Note: the SDK has no external_locations.validate(). Validate the underlying storage
# credential against the target URL (above); UC also checks access when the external
# location is created or updated.
```

```bash
# CLI: list / get / validate external locations
databricks external-locations list
databricks external-locations get my_s3_location

# Create via --json (order-independent, version-stable)
databricks external-locations create --json '{
  "name": "my_s3_location",
  "url": "s3://my-bucket/analytics",
  "credential_name": "my_s3_cred"
}'
```

> **CLI surface varies by version.** If `databricks external-locations`/`storage-credentials`
> is missing a subcommand, use the SQL DDL or the Python SDK shown above.

## What Builds on External Locations

- **External tables** — `CREATE TABLE … LOCATION 's3://my-bucket/analytics/orders'` (the path must sit under a registered external location). See [3-securables-ddl.md](3-securables-ddl.md).
- **External volumes** — `CREATE EXTERNAL VOLUME … LOCATION 's3://my-bucket/analytics/files'`. See [6-volumes.md](6-volumes.md).
- **External lineage** — register lineage to/from systems backed by external paths. See [5-system-tables.md](5-system-tables.md).

## Granting Access to External Locations

External locations are securables (see [1-access-control.md](1-access-control.md)). Grant the
path-level file privileges plus the right to create externals on them:

```sql
-- Read/write files directly under the location
GRANT READ FILES ON EXTERNAL LOCATION my_s3_location TO `data_engineers`;
GRANT WRITE FILES ON EXTERNAL LOCATION my_s3_location TO `data_engineers`;

-- Allow creating external tables/volumes on the location
GRANT CREATE EXTERNAL TABLE ON EXTERNAL LOCATION my_s3_location TO `data_engineers`;
GRANT CREATE EXTERNAL VOLUME ON EXTERNAL LOCATION my_s3_location TO `data_engineers`;
```

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    SecurableType,
    PermissionsChange,
    Privilege,
)

w = WorkspaceClient()
w.grants.update(
    securable_type=SecurableType.EXTERNAL_LOCATION,
    full_name="my_s3_location",
    changes=[
        PermissionsChange(
            principal="data_engineers",
            add=[Privilege.READ_FILES, Privilege.WRITE_FILES],
        )
    ],
)
```

## Troubleshooting / Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PERMISSION_DENIED` validating a credential | Cloud IAM trust policy / role not configured for UC | Fix the trust relationship (AWS) / access connector role assignment (Azure) / SA binding (GCP), then re-validate |
| `Overlapping external location` on create | The URL is nested under (or contains) an existing external location | Reuse the parent location, or create at a non-overlapping prefix |
| `Cannot create external table: path not in any external location` | Table `LOCATION` path is not covered by a registered external location | Create the external location first, then the table |
| `STORAGE_CREDENTIAL_DOES_NOT_EXIST` | Credential name typo, or it exists in another metastore | `databricks storage-credentials list` to confirm name + metastore |
| Validate returns `SKIP` for write | Credential is read-only for that path | Grant write at the cloud layer if writes are required |

## Best Practices

1. **One credential per cloud identity, reused by many locations** — don't create a credential per bucket if one IAM role already covers them.
2. **Always validate** after create/rotate — catch trust-policy mistakes early.
3. **Scope external locations tightly** — register the narrowest prefix a workload needs; overlapping locations are rejected.
4. **Grant `READ FILES`/`WRITE FILES` to groups** and `CREATE EXTERNAL …` only to teams that provision storage.
5. **Govern, don't hardcode** — reference data through external tables/volumes on these locations rather than embedding raw `s3://`/`abfss://` paths in jobs.

## Related

- [1-access-control.md](1-access-control.md) — the privilege model these grants belong to
- [3-securables-ddl.md](3-securables-ddl.md) — external table DDL on these locations
- [6-volumes.md](6-volumes.md) — external volume specifics
- **databricks-iceberg** — Iceberg REST Catalog credential *vending* for external engines (different concept)
