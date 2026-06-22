# Multi-source workload enumeration (`bundle_config.py`)

Some demos and customer bundles do not keep all their notebooks in the local source tree. Instead, they declare upstream git repos (or S3 paths) in a `bundle_config.py` file and pull the real task notebooks from there at install or deploy time. The skill must enumerate those upstream sources up front, before per-notebook analysis (Step 1.5), or it will mis-enumerate the workload and miss the real notebooks.

Source: 7-demo dbdemos E2E sweep. The clearest example is `dbt-on-databricks`: its `bundle_config.py` references `https://github.com/databricks-demos/dbt-databricks-c360`, and the real task notebooks (`01-load-data.py`, `03-churn-prediction.py`, etc.) live in that upstream repo, not in the local `dbdemos-notebooks/` tree.

## Detect

In Step 1.5 ("Enumerate first"), check for a `bundle_config.py` file at the top of the workload tree. If present, parse it for upstream-source declarations. Common declaration patterns:

- A `git_source` block: a dict with `git_url`, `git_provider`, `git_branch` keys.
- An `init_scripts` block referencing an upstream URL.
- A custom upstream-repo list, e.g., `external_repos = [{"url": "https://...", "ref": "main"}]`.
- S3 paths or workspace paths in any "source" field.

Parse `bundle_config.py` **statically, via `ast.parse(...)` only**. Walk the resulting AST for top-level `ast.Assign` nodes and use `ast.literal_eval` on right-hand-side literals (`dict`, `list`, `str`) to recover values. **Never `exec`, `eval`, or `import` the file** — it is workload-supplied Python source and may be untrusted; running it would be arbitrary code execution on the host. After recovering top-level literal values, scan them for any string that looks like a git URL (`https://github.com/...`, `git@github.com:...`) or a cloud storage path (`s3://`, `abfss://`, `gs://`).

## Procedure

1. **Parse `bundle_config.py`** via `ast.parse` for any upstream-source declarations (see safety note above).
2. **Show the parsed external sources to the user and require explicit confirmation before any fetch.** Print every git URL, S3/ADLS path, and workspace path you found, and wait for the user to approve. Do not auto-fetch without approval — these URLs come from the workload's own config and may point anywhere.
3. **For each user-approved upstream source**:
   - **Git URL**: `git clone <url>` into a sibling location (e.g., `~/.databricks-migration-skill/scratch/<run-id>/external/<repo-name>/`). Honor the declared branch/ref.
   - **S3/ADLS path**: download via `databricks fs cp -r <path> <local>` into the same sibling location.
   - **Workspace path**: export via `databricks workspace export-dir <path> <local>`.
4. **List external sources as a first-class artifact category** in the migration plan, alongside notebooks, jobs, pipelines. Use a category like `external_sources[]` with each entry containing `source_type` (git / s3 / workspace), `url_or_path`, `ref` (if git), and `local_path` (where you put it).
5. **Include external-source notebooks in the per-notebook enumeration** (Step 1.5 procedure step 1). Treat them exactly the same as local notebooks: read full source, run Step 2 Analyze, record the structured summary.
6. **When applying fixes**: write fixes back to the local clone of the external source. Track the upstream-vs-local mapping so the agent can produce a coherent migration plan.

## Example

`bundle_config.py` in `dbt-on-databricks`:

```python
# bundle_config.py (excerpt)
bundle_name = "dbt-on-databricks"

dbt_project_external = {
    "url": "https://github.com/databricks-demos/dbt-databricks-c360",
    "ref": "main",
    "subdirectory": "dbt-databricks-c360",
}

notebooks = [
    "_resources/00-setup.py",
    "01-wrapper-notebook.py",
]
```

**Skill behavior**:

1. Parse `bundle_config.py`, detect `dbt_project_external.url`.
2. `git clone https://github.com/databricks-demos/dbt-databricks-c360 ~/.databricks-migration-skill/scratch/<run-id>/external/dbt-databricks-c360/`.
3. Enumerate notebooks from BOTH the local tree (`_resources/00-setup.py`, `01-wrapper-notebook.py`) AND the cloned `dbt-databricks-c360` tree (`01-load-data.py`, `03-churn-prediction.py`, models / seeds / macros if any).
4. Migration plan lists the upstream repo as a first-class artifact and tracks the per-notebook fixes against the local clone.
5. **Job-spec migration (H1)**: rewrite `dbt_task.project_directory` to point at the **migrated** workspace location after deploy, e.g., `/Workspace/Users/<me>/dbt-on-databricks-skill-migrated/dbt-databricks-c360`.

## Verification

After Step 1.5 completes for a multi-source workload, verify the enumeration covers all real task notebooks:
- The enumeration includes notebooks from every upstream source declared in `bundle_config.py`.
- The migration plan's `external_sources[]` list is non-empty when `bundle_config.py` was present.
- No "real" task notebook (referenced by the job spec or the SDP pipeline spec) is missing from the per-notebook summary list.

## Documentation

- Databricks Asset Bundles: https://docs.databricks.com/en/dev-tools/bundles/index.html
- `databricks workspace export-dir`: https://docs.databricks.com/dev-tools/cli/workspace-commands.html
- `databricks fs cp`: https://docs.databricks.com/dev-tools/cli/fs-commands.html
