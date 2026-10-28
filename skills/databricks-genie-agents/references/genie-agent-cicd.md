# Genie Agent CI/CD

Reference for export, import, cross-workspace migration, batch migration, and CI/CD workflows for Genie Agents. For the `serialized_space` field shapes, see [create-genie-agent.md § serialized_space Format](create-genie-agent.md#serialized_space-format).

## Export & Import

**Convention:** `genie_agent.json` holds the **parsed** agent object (not a JSON-string-encoded blob), so it's readable and editable. Pass it as a compact JSON string (`jq -c`) to the `SERIALIZED_SPACE` positional (create) or the `--serialized-space` flag (update). `jq -r '.serialized_space | fromjson'` on export strips the outer quoting so the file is already a parsed object.

```bash
# Export: extract serialized_space AND unwrap it to a parsed object on disk
databricks genie get-space SPACE_ID --include-serialized-space -o json \
  | jq '.serialized_space | fromjson' > genie_agent.json

# Import / clone (WAREHOUSE_ID + serialized_space positional; rest are flags)
databricks workspace mkdirs /Workspace/Users/you@company.com/genie_spaces
databricks genie create-space WAREHOUSE_ID "$(jq -c . genie_agent.json)" \
  --title "Sales Analytics" \
  --description "Migrated agent" \
  --parent-path /Workspace/Users/you@company.com/genie_spaces

# Update an existing agent with a new config (--serialized-space is a full replacement)
databricks genie update-space SPACE_ID --serialized-space "$(jq -c . genie_agent.json)"
```

**Permissions required:**

| Operation | Required Permission |
|-----------|-------------------|
| Export (`get-space --include-serialized-space`) | CAN EDIT on source space |
| Import / clone (`create-space`) | Can create items in target workspace folder |
| Update (`update-space` with `serialized_space`) | CAN EDIT on target space |

## Cross-Workspace Migration

When migrating between workspaces, catalog names often differ. The catalog name appears everywhere inside `serialized_space` — table identifiers, SQL queries, join specs, and filter snippets. A single `.replace()` on the whole string covers all occurrences.

```bash
# Export from source workspace
DATABRICKS_CONFIG_PROFILE=source_profile \
  databricks genie get-space SPACE_ID --include-serialized-space -o json \
  | jq '.serialized_space | fromjson' > genie_agent.json

# Remap catalog name
python3 -c "import sys; p=sys.argv[1]; s=open(p).read(); open(p,'w').write(s.replace('source_catalog','target_catalog'))" genie_agent.json

# Import to target workspace
DATABRICKS_CONFIG_PROFILE=target_profile \
  databricks genie create-space TARGET_WAREHOUSE_ID "$(jq -c . genie_agent.json)" \
    --title "Sales Analytics" \
    --description "Migrated agent" \
    --parent-path /Workspace/Users/you@company.com/genie_spaces
```

Use `DATABRICKS_CONFIG_PROFILE=profile_name` to target different workspaces per operation.

**Agents with documents:** the remap also rewrites `/Volumes/<catalog>/...` paths, but the files don't move. Create the managed volume in the target and upload the files first; `create-space` then indexes it (wait for indexing before validating, see [create-genie-agent.md § Documents](create-genie-agent.md#documents-uc-volumes)).

## Batch Migration

To migrate multiple agents, loop through space IDs:

```bash
for SPACE_ID in id1 id2 id3; do
  # Export
  databricks genie get-space "$SPACE_ID" --include-serialized-space -o json \
    | jq '.serialized_space | fromjson' > "genie_${SPACE_ID}.json"

  # Remap catalog
  python3 -c "import sys; p=sys.argv[1]; s=open(p).read(); open(p,'w').write(s.replace('source_catalog','target_catalog'))" "genie_${SPACE_ID}.json"

  # Import
  TITLE=$(databricks genie get-space "$SPACE_ID" -o json | jq -r '.title')
  databricks genie create-space TARGET_WAREHOUSE_ID "$(jq -c . "genie_${SPACE_ID}.json")" \
    --title "$TITLE" \
    --parent-path /Workspace/Users/you@company.com/genie_spaces
done
```

After migration, update `databricks.yml` with the new space IDs under the target's `genie_space_ids` variable.

## Declarative Automation Bundles (DABs, formerly Databricks Asset Bundles)

To manage Genie Agents as code in a DAB, reference the space ID in `databricks.yml` and use the export/import pattern above in CI/CD pipelines. Store `genie_agent.json` in version control alongside the bundle.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Empty `serialized_space` on export | Requires CAN EDIT permission on the agent |
| Tables not found after migration | Remap catalog name in `serialized_space` before import — catalog appears in table identifiers, SQL, join specs, and filter snippets |
| JSON parse error on import | `serialized_space` may contain multi-line SQL with `\n` sequences — flatten SQL arrays to single-line strings before passing |
