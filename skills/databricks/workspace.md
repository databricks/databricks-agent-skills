# Workspace

The Databricks workspace contains notebooks, directories, and files.

## Workspace Commands

### List Contents

```bash
# List workspace directory contents
databricks workspace list /Users/user@example.com --profile my-workspace

# List root
databricks workspace list / --profile my-workspace

# List Shared folder
databricks workspace list /Shared --profile my-workspace
```

### Get Object Status

```bash
# Get details about workspace object
databricks workspace get-status --path /Users/user@example.com/notebook --profile my-workspace
```

## Export and Import

### Export Notebook

```bash
# Export notebook (SOURCE format)
databricks workspace export /Users/user@example.com/notebook \
  --format SOURCE \
  --profile my-workspace

# Export to file
databricks workspace export /Users/user@example.com/notebook \
  --format SOURCE \
  -o notebook.py \
  --profile my-workspace

# Export as HTML
databricks workspace export /Users/user@example.com/notebook \
  --format HTML \
  -o notebook.html \
  --profile my-workspace

# Export as Jupyter notebook
databricks workspace export /Users/user@example.com/notebook \
  --format JUPYTER \
  -o notebook.ipynb \
  --profile my-workspace
```

### Export Directory

```bash
# Export entire directory
databricks workspace export_dir /Users/user@example.com/notebooks \
  ./local-notebooks \
  --profile my-workspace
```

### Import Notebook

```bash
# Import notebook
databricks workspace import notebook.py \
  /Users/user@example.com/notebook \
  --language PYTHON \
  --format SOURCE \
  --profile my-workspace

# Import and overwrite existing
databricks workspace import notebook.py \
  /Users/user@example.com/notebook \
  --language PYTHON \
  --format SOURCE \
  --overwrite \
  --profile my-workspace
```

### Import Directory

```bash
# Import entire directory
databricks workspace import_dir ./local-notebooks \
  /Users/user@example.com/notebooks \
  --profile my-workspace

# Import with overwrite
databricks workspace import_dir ./local-notebooks \
  /Users/user@example.com/notebooks \
  --overwrite \
  --profile my-workspace
```

## File Formats

### SOURCE

Native notebook format (Python, Scala, SQL, R files with magic commands).

```bash
databricks workspace export /path/to/notebook \
  --format SOURCE \
  -o notebook.py \
  --profile my-workspace
```

### HTML

HTML export of notebook with outputs.

```bash
databricks workspace export /path/to/notebook \
  --format HTML \
  -o notebook.html \
  --profile my-workspace
```

### JUPYTER

Jupyter notebook format (.ipynb).

```bash
databricks workspace export /path/to/notebook \
  --format JUPYTER \
  -o notebook.ipynb \
  --profile my-workspace
```

### DBC

Databricks archive format (for directories).

```bash
databricks workspace export /path/to/directory \
  --format DBC \
  -o directory.dbc \
  --profile my-workspace
```

## Directory Management

### Create Directory

```bash
# Create directory
databricks workspace mkdirs /Users/user@example.com/new-folder --profile my-workspace

# Create nested directories
databricks workspace mkdirs /Users/user@example.com/path/to/folder --profile my-workspace
```

### Delete Objects

```bash
# Delete notebook or file
databricks workspace delete /Users/user@example.com/notebook --profile my-workspace

# Delete directory recursively
databricks workspace delete /Users/user@example.com/folder --recursive --profile my-workspace
```

## Workspace Structure

```
/
├── Users/
│   └── user@example.com/
│       ├── notebooks/
│       ├── scripts/
│       └── experiments/
├── Shared/
│   ├── team-notebooks/
│   └── common-libraries/
└── Repos/
    └── username/
        └── repository-name/
```

## Common Workflows

### Backup Notebooks

```bash
# Export all notebooks to local directory
databricks workspace export_dir /Users/user@example.com \
  ./backup/$(date +%Y%m%d) \
  --profile my-workspace
```

### Sync Local Development

```bash
# Export from workspace
databricks workspace export_dir /Users/user@example.com/project \
  ./local-project \
  --profile my-workspace

# Make changes locally

# Import back to workspace
databricks workspace import_dir ./local-project \
  /Users/user@example.com/project \
  --overwrite \
  --profile my-workspace
```

### Migrate Notebooks Between Workspaces

```bash
# Export from source workspace
databricks workspace export_dir /Shared/project \
  ./project-backup \
  --profile source-workspace

# Import to target workspace
databricks workspace import_dir ./project-backup \
  /Shared/project \
  --profile target-workspace
```

## Using with Asset Bundles

Asset Bundles can automatically sync notebooks:

```yaml
# databricks.yml
bundle:
  name: my-project

workspace:
  file_path: ./src
```

This syncs `./src` directory to workspace during deployment.

## Best Practices

### 1. Organize by Purpose

```
/Users/user@example.com/
├── development/    # Active development
├── production/     # Production notebooks
├── experiments/    # Ad-hoc analysis
└── archive/        # Old notebooks
```

### 2. Use Shared for Team Collaboration

```
/Shared/
├── analytics-team/
├── ml-team/
└── common-libraries/
```

### 3. Regular Backups

```bash
# Daily backup script
databricks workspace export_dir /Users/user@example.com \
  ./backups/$(date +%Y%m%d) \
  --profile my-workspace
```

### 4. Use Repos for Version Control

Prefer Repos over direct workspace notebooks:

```
/Repos/
└── username/
    └── my-project/    # Git repository
        ├── notebooks/
        ├── src/
        └── tests/
```

### 5. Descriptive Names

```bash
# ✅ Good: Descriptive names
customer_analysis_monthly.py
etl_pipeline_v2.py
feature_engineering_model_a.py

# ❌ Avoid: Generic names
notebook1.py
test.py
untitled.py
```

### 6. Use Asset Bundles

Prefer Asset Bundles for managing workspace content:
- Version control
- Automated deployment
- Environment management

## Troubleshooting

### Export Fails

**Symptom**: `databricks workspace export` fails

**Solution**:
1. Verify path exists
2. Check you have read permissions
3. Ensure output directory exists locally
4. Check for special characters in filename

### Import Fails

**Symptom**: `databricks workspace import` fails

**Solution**:
1. Verify file exists locally
2. Check language is correct
3. Ensure parent directory exists in workspace
4. Use `--overwrite` if object already exists
5. Verify format is correct

### Permission Denied

**Symptom**: Cannot access workspace path

**Solution**:
1. Verify you have permissions on the path
2. Check if path belongs to another user
3. Use /Shared for team collaboration
4. Contact workspace admin for access

### Directory Not Empty

**Symptom**: Cannot delete directory

**Solution**:
```bash
# Use --recursive flag
databricks workspace delete /path/to/folder --recursive --profile my-workspace
```

## Notebook Languages

Databricks supports multiple languages:

- **Python**: `.py`
- **Scala**: `.scala`
- **SQL**: `.sql`
- **R**: `.r`

Specify language when importing:

```bash
databricks workspace import notebook.py \
  /path/in/workspace \
  --language PYTHON \
  --format SOURCE \
  --profile my-workspace
```

## Magic Commands in Notebooks

Notebooks support magic commands:

```python
# %md - Markdown cell
# %md
# # Heading
# This is markdown content

# %sql - SQL cell
# %sql
# SELECT * FROM table

# %sh - Shell command
# %sh
# ls -la

# %fs - Filesystem command
# %fs ls /mnt/data/

# %run - Run another notebook
# %run ./shared_functions
```

## Related Topics

- [Asset Bundles](asset-bundles.md) - Manage workspace content as code
- [Repos](https://docs.databricks.com/repos/) - Git integration
- [Jobs](jobs.md) - Schedule notebook execution
- [Clusters](clusters.md) - Run notebooks on clusters
