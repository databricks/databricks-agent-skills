# DBFS (Databricks File System)

DBFS provides distributed file storage for Databricks workspaces.

**Note**: For new projects, prefer **Unity Catalog Volumes** over DBFS for better governance and access control.

## DBFS Commands

### List Files

```bash
# List files and directories
databricks fs ls dbfs:/path/ --profile my-workspace

# List root
databricks fs ls dbfs:/ --profile my-workspace

# List FileStore
databricks fs ls dbfs:/FileStore/ --profile my-workspace
```

### Copy Files

```bash
# Copy file to DBFS
databricks fs cp local-file.txt dbfs:/path/file.txt --profile my-workspace

# Copy file from DBFS
databricks fs cp dbfs:/path/file.txt local-file.txt --profile my-workspace

# Copy directory recursively
databricks fs cp -r ./local-dir/ dbfs:/path/dir/ --profile my-workspace

# Overwrite existing file
databricks fs cp --overwrite local-file.txt dbfs:/path/file.txt --profile my-workspace
```

### Move/Rename Files

```bash
# Move or rename file
databricks fs mv dbfs:/path/old.txt dbfs:/path/new.txt --profile my-workspace

# Move directory
databricks fs mv dbfs:/old-path/ dbfs:/new-path/ --profile my-workspace
```

### Remove Files

```bash
# Remove file
databricks fs rm dbfs:/path/file.txt --profile my-workspace

# Remove directory recursively
databricks fs rm -r dbfs:/path/directory/ --profile my-workspace

# Remove without confirmation
databricks fs rm --skip-trash dbfs:/path/file.txt --profile my-workspace
```

### Create Directory

```bash
# Create directory
databricks fs mkdirs dbfs:/path/new-directory/ --profile my-workspace

# Create nested directories
databricks fs mkdirs dbfs:/path/to/nested/directory/ --profile my-workspace
```

### Cat (View File Contents)

```bash
# View file contents
databricks fs cat dbfs:/path/file.txt --profile my-workspace
```

## DBFS Paths

### Common DBFS Locations

```
dbfs:/
├── FileStore/           # User uploads (accessible via HTTP)
├── databricks-datasets/ # Sample datasets
├── mnt/                 # Mount points for cloud storage
├── tmp/                 # Temporary files
└── user/                # User-specific directories
```

### FileStore

Files in `/FileStore` are accessible via HTTP:

```bash
# Upload to FileStore
databricks fs cp image.png dbfs:/FileStore/images/image.png --profile my-workspace

# Access via URL
# https://<workspace-url>/files/images/image.png
```

### Mounts

Mount external cloud storage:

```python
# Mount S3 bucket (run in notebook)
dbutils.fs.mount(
  source = "s3a://my-bucket/path",
  mount_point = "/mnt/my-data",
  extra_configs = {
    "fs.s3a.access.key": dbutils.secrets.get("my-scope", "aws-access-key"),
    "fs.s3a.secret.key": dbutils.secrets.get("my-scope", "aws-secret-key")
  }
)
```

```bash
# List mounted storage
databricks fs ls dbfs:/mnt/ --profile my-workspace
```

## DBFS vs Unity Catalog Volumes

### Use Unity Catalog Volumes (Recommended)

✅ **Advantages**:
- Fine-grained access control
- Cross-workspace data sharing
- Audit logging
- Data governance
- Better security

```bash
# Unity Catalog Volume path
databricks fs ls dbfs:/Volumes/<catalog>/<schema>/<volume>/ --profile my-workspace
```

### Use DBFS (Legacy)

❌ **Limitations**:
- Workspace-scoped only
- Limited access control
- No audit logging
- Being phased out for new features

```bash
# Legacy DBFS path
databricks fs ls dbfs:/user/data/ --profile my-workspace
```

## Common Workflows

### Upload Data Files

```bash
# Upload CSV
databricks fs cp data.csv dbfs:/FileStore/data/data.csv --profile my-workspace

# Upload multiple files
for file in *.csv; do
  databricks fs cp "$file" "dbfs:/FileStore/data/$file" --profile my-workspace
done
```

### Download Results

```bash
# Download output file
databricks fs cp dbfs:/output/results.csv ./results.csv --profile my-workspace
```

### Manage Libraries

```bash
# Upload Python wheel
databricks fs cp my_package-0.1.0-py3-none-any.whl \
  dbfs:/FileStore/wheels/my_package.whl \
  --profile my-workspace

# Upload JAR
databricks fs cp my-library.jar \
  dbfs:/FileStore/jars/my-library.jar \
  --profile my-workspace
```

### Backup DBFS Data

```bash
# Download directory
databricks fs cp -r dbfs:/important-data/ ./backup/ --profile my-workspace
```

## Best Practices

### 1. Prefer Unity Catalog Volumes

For new projects, always use Unity Catalog Volumes:

```bash
# ✅ Good: Unity Catalog Volume
databricks fs cp data.csv \
  dbfs:/Volumes/my_catalog/my_schema/my_volume/data.csv \
  --profile my-workspace

# ❌ Avoid: Direct DBFS
databricks fs cp data.csv dbfs:/data/data.csv --profile my-workspace
```

### 2. Use Mounts for External Storage

Mount cloud storage instead of copying:

```python
# Mount once, access many times
dbutils.fs.mount(
  source = "s3a://my-bucket/data",
  mount_point = "/mnt/production-data"
)
```

### 3. Organize Files

```
dbfs:/FileStore/
├── data/
│   ├── raw/
│   ├── processed/
│   └── archive/
├── wheels/
├── jars/
└── init-scripts/
```

### 4. Clean Up Temporary Files

```bash
# Remove old temp files
databricks fs rm -r dbfs:/tmp/old-files/ --profile my-workspace
```

### 5. Use Appropriate Storage

- **Small files, temporary**: DBFS
- **Large datasets, governed**: Unity Catalog Volumes
- **External data lakes**: Mounts or External Volumes

## Troubleshooting

### File Not Found

**Symptom**: `Error: File not found`

**Solution**:
1. Check path is correct (case-sensitive)
2. Verify file exists: `databricks fs ls`
3. Check you have read permissions
4. Ensure path starts with `dbfs:/`

### Permission Denied

**Symptom**: `Error: Permission denied`

**Solution**:
1. For UC Volumes, check grants on volume
2. For DBFS, check workspace permissions
3. Verify you're using correct workspace/profile
4. Contact workspace admin for access

### Upload Fails

**Symptom**: File upload fails or times out

**Solution**:
1. Check file size (large files may timeout)
2. Verify network connection
3. Use `--overwrite` if file exists
4. Try uploading to different path
5. Split large files into smaller chunks

### Mount Fails

**Symptom**: Cannot mount external storage

**Solution**:
1. Verify cloud credentials are correct
2. Check bucket/container permissions
3. Ensure secrets are properly configured
4. Verify IAM roles (AWS) or service principals (Azure)
5. Check mount point doesn't already exist

## DBFS Limitations

1. **No POSIX compliance**: Not a full POSIX filesystem
2. **Limited permissions**: Basic workspace-level access control
3. **No versioning**: No built-in file versioning
4. **Workspace-scoped**: Cannot share across workspaces
5. **Being deprecated**: Gradually replaced by Unity Catalog Volumes

## Migration to Unity Catalog Volumes

### 1. Create Volume

```bash
databricks volumes create my_volume \
  --catalog-name my_catalog \
  --schema-name my_schema \
  --volume-type MANAGED \
  --profile my-workspace
```

### 2. Copy Data

```bash
# Copy from DBFS to UC Volume
databricks fs cp -r dbfs:/old-data/ \
  dbfs:/Volumes/my_catalog/my_schema/my_volume/data/ \
  --profile my-workspace
```

### 3. Update References

Update notebooks and jobs to use new paths:

```python
# Old DBFS path
df = spark.read.csv("dbfs:/data/customers.csv")

# New UC Volume path
df = spark.read.csv("dbfs:/Volumes/my_catalog/my_schema/my_volume/customers.csv")
```

### 4. Set Permissions

```bash
databricks grants update \
  --securable-type VOLUME \
  --full-name my_catalog.my_schema.my_volume \
  --principal data-team \
  --privilege READ_VOLUME \
  --profile my-workspace
```

## Alternative: Use Cloud Storage Directly

For better governance, access cloud storage directly through Unity Catalog:

### AWS S3

```python
# Configure external location in Unity Catalog
# Then access directly
df = spark.read.csv("s3://my-bucket/data.csv")
```

### Azure ADLS

```python
# Configure external location in Unity Catalog
# Then access directly
df = spark.read.csv("abfss://container@storage.dfs.core.windows.net/data.csv")
```

### GCS

```python
# Configure external location in Unity Catalog
# Then access directly
df = spark.read.csv("gs://my-bucket/data.csv")
```

## Related Topics

- [Unity Catalog](unity-catalog.md) - Preferred alternative to DBFS
- [Workspace](workspace.md) - Manage workspace files
- [Clusters](clusters.md) - Access DBFS from clusters
