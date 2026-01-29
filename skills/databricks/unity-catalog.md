# Unity Catalog

Unity Catalog provides unified governance for data and AI assets across Databricks workspaces.

## Catalogs

Catalogs are the top-level containers in Unity Catalog's three-level namespace (catalog.schema.table).

```bash
# List catalogs
databricks catalogs list --profile my-workspace

# Get catalog details
databricks catalogs get <catalog-name> --profile my-workspace

# Create a catalog
databricks catalogs create <catalog-name> --profile my-workspace

# Create a catalog with comment
databricks catalogs create <catalog-name> --comment "Production catalog" --profile my-workspace

# Update a catalog
databricks catalogs update <catalog-name> --comment "Updated catalog" --profile my-workspace

# Delete a catalog
databricks catalogs delete <catalog-name> --profile my-workspace
```

## Schemas

Schemas (also called databases) organize tables and views within a catalog.

```bash
# List schemas in a catalog (positional argument!)
databricks schemas list <catalog-name> --profile my-workspace

# Get schema details
databricks schemas get <catalog-name>.<schema-name> --profile my-workspace

# Create a schema
databricks schemas create <catalog-name>.<schema-name> --profile my-workspace

# Create a schema with comment
databricks schemas create <catalog-name>.<schema-name> --comment "Analytics schema" --profile my-workspace

# Update a schema
databricks schemas update <catalog-name>.<schema-name> --comment "Updated schema" --profile my-workspace

# Delete a schema
databricks schemas delete <catalog-name>.<schema-name> --profile my-workspace
```

## Tables

Tables store structured data in Unity Catalog.

```bash
# List tables in a schema (positional arguments!)
databricks tables list <catalog-name> <schema-name> --profile my-workspace

# Get table details
databricks tables get <catalog-name>.<schema-name>.<table-name> --profile my-workspace

# Delete a table
databricks tables delete <catalog-name>.<schema-name>.<table-name> --profile my-workspace
```

**Note**: Tables are typically created using SQL or Spark DataFrames, not directly through the CLI.

## Volumes

Unity Catalog Volumes provide managed storage for non-tabular data (files, images, models, etc.).

### Volume Commands

```bash
# List volumes in a schema (positional arguments!)
databricks volumes list <catalog-name> <schema-name> --profile my-workspace

# Get volume details
databricks volumes get <catalog-name>.<schema-name>.<volume-name> --profile my-workspace

# Create a managed volume
databricks volumes create <volume-name> \
  --catalog-name <catalog-name> \
  --schema-name <schema-name> \
  --volume-type MANAGED \
  --profile my-workspace

# Create an external volume
databricks volumes create <volume-name> \
  --catalog-name <catalog-name> \
  --schema-name <schema-name> \
  --volume-type EXTERNAL \
  --storage-location s3://my-bucket/path/ \
  --profile my-workspace

# Update a volume
databricks volumes update <catalog-name>.<schema-name>.<volume-name> \
  --comment "Updated volume" \
  --profile my-workspace

# Delete a volume
databricks volumes delete <catalog-name>.<schema-name>.<volume-name> --profile my-workspace
```

### Working with Volume Files

Volumes can be accessed like directories using DBFS-style paths:

```bash
# List files in a volume
databricks fs ls dbfs:/Volumes/<catalog>/<schema>/<volume>/ --profile my-workspace

# Upload file to volume
databricks fs cp local-file.csv \
  dbfs:/Volumes/<catalog>/<schema>/<volume>/file.csv \
  --profile my-workspace

# Download file from volume
databricks fs cp dbfs:/Volumes/<catalog>/<schema>/<volume>/file.csv \
  local-file.csv \
  --profile my-workspace

# Delete file from volume
databricks fs rm dbfs:/Volumes/<catalog>/<schema>/<volume>/file.csv --profile my-workspace
```

### Volume Types

**MANAGED Volume**:
- Storage managed by Databricks
- Data deleted when volume is deleted
- Recommended for most use cases

**EXTERNAL Volume**:
- Points to external cloud storage (S3, ADLS, GCS)
- Data persists after volume deletion
- Useful for existing data lakes

## Functions

Unity Catalog can manage user-defined functions (UDFs).

```bash
# List functions in a schema
databricks functions list --catalog-name <catalog-name> --schema-name <schema-name> --profile my-workspace

# Get function details
databricks functions get <catalog-name>.<schema-name>.<function-name> --profile my-workspace
```

**Note**: Functions are typically created using SQL or Spark, not directly through the CLI.

## Grants and Permissions

Unity Catalog uses a fine-grained permission model.

### Grant Commands

```bash
# Get grants on a securable object
databricks grants get --securable-type <type> --full-name <name> --profile my-workspace

# Grant permissions
databricks grants update \
  --securable-type <type> \
  --full-name <name> \
  --principal <principal> \
  --privilege <privilege> \
  --profile my-workspace
```

### Securable Types

- `CATALOG` - Catalog
- `SCHEMA` - Schema/Database
- `TABLE` - Table or View
- `VOLUME` - Volume
- `FUNCTION` - Function
- `EXTERNAL_LOCATION` - External location

### Common Privileges

**Catalog-level**:
- `USE_CATALOG` - Access catalog
- `CREATE_SCHEMA` - Create schemas in catalog
- `USE_SCHEMA` - Access schemas in catalog

**Schema-level**:
- `USE_SCHEMA` - Access schema
- `CREATE_TABLE` - Create tables in schema
- `CREATE_VOLUME` - Create volumes in schema
- `CREATE_FUNCTION` - Create functions in schema

**Table-level**:
- `SELECT` - Read table data
- `MODIFY` - Insert/update/delete data
- `READ_METADATA` - Read table metadata

**Volume-level**:
- `READ_VOLUME` - Read files from volume
- `WRITE_VOLUME` - Write files to volume

### Grant Examples

```bash
# Grant catalog access to a user
databricks grants update \
  --securable-type CATALOG \
  --full-name my_catalog \
  --principal user@example.com \
  --privilege USE_CATALOG \
  --profile my-workspace

# Grant schema creation to a group
databricks grants update \
  --securable-type CATALOG \
  --full-name my_catalog \
  --principal data-engineers-group \
  --privilege CREATE_SCHEMA \
  --profile my-workspace

# Grant table read access
databricks grants update \
  --securable-type TABLE \
  --full-name my_catalog.my_schema.my_table \
  --principal analysts-group \
  --privilege SELECT \
  --profile my-workspace

# Grant volume write access
databricks grants update \
  --securable-type VOLUME \
  --full-name my_catalog.my_schema.my_volume \
  --principal ml-team-group \
  --privilege WRITE_VOLUME \
  --profile my-workspace
```

## Unity Catalog Hierarchy

```
Workspace
└── Metastore (one per region)
    └── Catalogs
        └── Schemas
            ├── Tables
            ├── Views
            ├── Volumes
            └── Functions
```

## Common Workflows

### Creating a Complete UC Structure

```bash
# 1. Create catalog
databricks catalogs create analytics_catalog --profile my-workspace

# 2. Create schema
databricks schemas create analytics_catalog.customer_data --profile my-workspace

# 3. Create volume for raw data
databricks volumes create raw_data \
  --catalog-name analytics_catalog \
  --schema-name customer_data \
  --volume-type MANAGED \
  --profile my-workspace

# 4. Upload data to volume
databricks fs cp customer_data.csv \
  dbfs:/Volumes/analytics_catalog/customer_data/raw_data/ \
  --profile my-workspace

# 5. Grant permissions
databricks grants update \
  --securable-type CATALOG \
  --full-name analytics_catalog \
  --principal data-team-group \
  --privilege USE_CATALOG \
  --profile my-workspace
```

### Setting Up Data Access for a Team

```bash
# Grant catalog access
databricks grants update \
  --securable-type CATALOG \
  --full-name production_catalog \
  --principal data-science-team \
  --privilege USE_CATALOG \
  --profile my-workspace

# Grant schema access
databricks grants update \
  --securable-type SCHEMA \
  --full-name production_catalog.features \
  --principal data-science-team \
  --privilege USE_SCHEMA \
  --profile my-workspace

# Grant table read
databricks grants update \
  --securable-type TABLE \
  --full-name production_catalog.features.customer_features \
  --principal data-science-team \
  --privilege SELECT \
  --profile my-workspace
```

## Best Practices

### 1. Use Three-Level Namespace

Always reference objects with the full three-level name:
- `catalog.schema.table`
- `catalog.schema.volume`
- `catalog.schema.function`

### 2. Prefer Volumes Over DBFS

For new projects:
- ✅ Use Unity Catalog Volumes
- ❌ Avoid direct DBFS usage

Volumes provide:
- Unified governance
- Fine-grained access control
- Cross-workspace sharing
- Audit logging

### 3. Organize by Environment

```
production_catalog
├── analytics_schema
├── ml_models_schema
└── reports_schema

staging_catalog
├── analytics_schema
├── ml_models_schema
└── reports_schema

dev_catalog
├── analytics_schema
├── ml_models_schema
└── reports_schema
```

### 4. Use Groups for Permissions

Grant permissions to groups, not individual users:

```bash
# ✅ Good: Grant to group
databricks grants update \
  --securable-type CATALOG \
  --full-name my_catalog \
  --principal data-engineers \
  --privilege USE_CATALOG \
  --profile my-workspace

# ❌ Avoid: Grant to individual users (hard to maintain)
```

### 5. Apply Least Privilege

Only grant necessary permissions:
- Don't grant `ALL PRIVILEGES` unless required
- Use read-only access (SELECT) when possible
- Separate read and write permissions

### 6. Document with Comments

```bash
# Add descriptions to objects
databricks catalogs create analytics \
  --comment "Production analytics catalog - contains all customer analytics data" \
  --profile my-workspace

databricks schemas create analytics.sales \
  --comment "Sales analytics - updated daily at 2 AM UTC" \
  --profile my-workspace
```

## Troubleshooting

### Permission Denied Errors

**Symptom**: `Error: PERMISSION_DENIED` when accessing UC resources

**Solution**:
1. Check grants: `databricks grants get --securable-type CATALOG --full-name <catalog> --profile my-workspace`
2. Verify you have necessary privileges (USE_CATALOG, USE_SCHEMA, SELECT, etc.)
3. Check if you're a member of required groups
4. Contact workspace admin to grant permissions

### Cannot Create Objects

**Symptom**: Cannot create tables/volumes/functions in schema

**Solution**:
1. Verify you have `USE_CATALOG` on the catalog
2. Verify you have `USE_SCHEMA` on the schema
3. Verify you have appropriate CREATE privilege (CREATE_TABLE, CREATE_VOLUME, etc.)

### Volume Path Not Found

**Symptom**: Cannot access volume path

**Solution**:
1. Verify volume exists: `databricks volumes get <catalog>.<schema>.<volume> --profile my-workspace`
2. Check path format: `dbfs:/Volumes/<catalog>/<schema>/<volume>/`
3. Verify you have READ_VOLUME or WRITE_VOLUME privilege
4. Ensure catalog and schema names are correct (case-sensitive)

## Related Topics

- [DBFS](dbfs.md) - File system operations
- [Asset Bundles](asset-bundles.md) - Define UC resources as code
- [Workflows](workflows.md) - Complete UC setup workflows
