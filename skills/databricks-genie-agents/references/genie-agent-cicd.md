# Genie Agent CI/CD

Reference for export, import, cross-workspace migration, batch migration, and CI/CD workflows for Genie Agents. For the `serialized_space` field shapes used in these operations, see [serialized-space.md](serialized-space.md).

## Export & Import

**Convention:** `genie_agent.json` always holds the **parsed** agent object (not a JSON-string-encoded blob), so it's readable and editable. Stringify it with `jq -c '.' | jq -Rs '.'` at each use site. `jq -r '.serialized_space | fromjson'` on export strips the outer quoting so the file is already a parsed object.

```bash
# Export: extract serialized_space AND unwrap it to a parsed object on disk
databricks genie get-space SPACE_ID --include-serialized-space -o json \
  | jq '.serialized_space | fromjson' > genie_agent.json

# Import / clone
databricks workspace mkdirs /Workspace/Users/you@company.com/genie_spaces
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Migrated agent\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')
}"

# Update an existing agent with a new config
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')}"
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
  databricks genie create-space --json "{
    \"warehouse_id\": \"TARGET_WAREHOUSE_ID\",
    \"title\": \"Sales Analytics\",
    \"description\": \"Migrated agent\",
    \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
    \"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')
  }"
```

Use `DATABRICKS_CONFIG_PROFILE=profile_name` to target different workspaces per operation.

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
  SS=$(cat "genie_${SPACE_ID}.json" | jq -c '.')
  databricks genie create-space --json "$(jq -n \
    --arg title "$TITLE" \
    --arg ss "$SS" \
    '{"warehouse_id": "TARGET_WAREHOUSE_ID", "title": $title, "parent_path": "/Workspace/Users/you@company.com/genie_spaces", "serialized_space": $ss}')"
done
```

After migration, update `databricks.yml` with the new space IDs under the target's `genie_space_ids` variable.

## Databricks Asset Bundles (DABs)

To manage Genie Agents as code in a DAB, reference the space ID in `databricks.yml` and use the export/import pattern above in CI/CD pipelines. Store `genie_agent.json` in version control alongside the bundle.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Empty `serialized_space` on export | Requires CAN EDIT permission on the agent |
| Tables not found after migration | Remap catalog name in `serialized_space` before import — catalog appears in table identifiers, SQL, join specs, and filter snippets |
| JSON parse error on import | `serialized_space` may contain multi-line SQL with `\n` sequences — flatten SQL arrays to single-line strings before passing |
