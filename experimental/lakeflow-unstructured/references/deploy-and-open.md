# Deploy and open in Document Intelligence

Use the current Databricks CLI and the user's selected workspace profile. The
workspace needs Document Intelligence, deployment history, and the requested
AI Function task types available. Use `databricks-core` for authentication and
`databricks-dabs` for general bundle commands. Keep every command on the same
profile and target.

## Configure the workspace folder

The [starting bundle](../assets/workflow/databricks.yml) sets:

```yaml
experimental:
  deployment_history: true

workspace:
  file_path: ${var.workflow_workspace_path}
  sync_mode: overwrite
```

Set `workflow_workspace_path` to the dedicated folder selected for the workflow,
for example `/Workspace/Users/<user>/document_processing`. Keep workflow files
in that folder, rather than directly in a home, Shared, or Repos parent folder.
Use an ordinary workflow folder outside deployment-state directories.

`workspace.file_path` is where a local bundle deploy publishes its files. The
manifest and bundle must be published together there so the workflow page can
associate its deployed resources. Keep the bundle's deployment state at its
separate default root; do not set `workspace.root_path` to the workflow folder.
The template explicitly includes the workflow metadata and Markdown in sync.

Enable deployment history before the first deploy and keep it enabled. For an
existing deployment, preserve its deployment-history configuration; if it was
created without history, agree on a migration before creating a replacement.

## Set workload variables

Copy the assets described in [Workflow folder](workflow-folder.md) to the local
workflow root. Adapt the bundle's name, manifest title, and requirements files.
Set these variables from the user's confirmed choices:

| Variable | Value |
| --- | --- |
| `workflow_workspace_path` | Dedicated workspace workflow folder |
| `input_volume_path` | Existing volume directory to parse; replace this variable when adapting to table input |
| `output_catalog` | Existing destination catalog |
| `output_schema` | Destination schema for this development workflow's outputs |
| `extraction_schema` | Confirmed field map, encoded as a JSON string |
| `extraction_instructions` | Instructions agreed for this workload |

Use the bundle variable mechanism documented by `databricks-dabs`. For local
values, `.databricks/bundle/dev/variable-overrides.json` is a JSON object keyed
by variable name; `extraction_schema` is a JSON-encoded string within that object.
Keep local configuration and credentials out of the published workflow files.

Verify source read access, destination catalog/schema access, the ability to
create output tables, and write access to the workspace workflow folder. Reuse
existing schemas; obtain approval before creating a missing one. Match the
Job's run identity to the required source and destination access.

## Validate and deploy development

Replace angle-bracket placeholders in the commands below with the selected
profile, folder, and returned resource IDs. Run bundle commands from the local
workflow root.

```bash
databricks bundle validate --strict --target dev --profile <profile>
databricks bundle plan --target dev --profile <profile>
```

Review the resolved inputs, output catalog/schema, extraction configuration,
and workspace file path. Confirm there are no unintended replacements or
changes to existing resources. When updating a workflow, reconcile edits made
in the UI before overwriting them with the local bundle.

Deploy the authorized development configuration:

```bash
databricks bundle deploy --target dev --profile <profile>
databricks bundle summary --target dev --profile <profile> --output json
databricks workspace get-status "<workflow_workspace_path>" --profile <profile> --output json
```

Record the returned Job ID, folder object ID, and URLs. Read the Job back with
`databricks jobs get <job_id> --profile <profile> --output json` and verify its
tasks, dependencies, source, output destination, and extraction schema.

A folder can also be published before deployment when the user asks to save
only its design. Use Workspace file operations from the CLI, preserving file
names and extensions, and report that resources have not been deployed.

## Open and verify the workflow

Use the selected profile's workspace URL and the folder's returned `object_id`
to build the workflow link:

```text
<workspace-url>/ingestion/document-intelligence/workflows/<folder-object-id>
```

Open it in the user's browser when available, or provide the link and ask the
user to verify the page. The workflow should also appear under **Data Ingestion
> Document Intelligence** after the workspace search index refreshes.

Check both the title/specification and the deployed Job/target association. Use
`bundle summary` to confirm the resource links agree with the workflow page.
If the page does not show the deployment, verify the workspace's deployment
history availability, the bundle's history setting, and the published folder
path. Report a pending UI check separately from a successful CLI deployment.

## Run and inspect when authorized

Establish the input size and test scope first, as described in
[Document processing](document-processing.md). Then:

```bash
databricks bundle run document_processing --target dev --profile <profile> --no-wait
databricks jobs get-run <run_id> --profile <profile> --output json
```

The template's Job resource key is `document_processing`; adapt the command if
that key changes. Provide the returned run link. Check task states and their
output tables before reporting execution success. Record validation results
and actual table names in the workflow files and deploy their updates.

For evaluation, improving extraction quality, and visual debugging, direct the
user to the workflow page and Genie Code. Include a short handoff describing
the current schema, input and output locations, test evidence, and next quality
questions.

## Production promotion

The starting template deploys development only. When the user asks to promote,
use `databricks-dabs` to add a production target with an explicit run identity,
separate output destinations and deployment state, and an agreed schedule.
Choose how production source files are published before deploying; edits to a
shared workspace file path affect resources that read those files. Validate
the production folder/deployment association and inspect the first run.
