# Workflow folder

A Document Intelligence workflow is a workspace folder containing a workflow
manifest and a Declarative Automation Bundle. The folder's workspace object ID
is the workflow ID. The bundle defines the Job and any supporting resources.

## Layout and starting files

Create a dedicated local directory and a corresponding workspace directory
inside the user's chosen parent folder. Use a descriptive `snake_case` name.
Reuse an existing workflow directory only when the user selected it.

```text
document_processing/
├── databricks.yml
├── udp_workflow.yaml
├── udp_workflow.schema.json
├── README.md
├── SPEC.md
├── AGENTS.md
└── src/                       # Add only for SQL, notebooks, or pipeline code
```

| Output file | Role | Starting asset |
| --- | --- | --- |
| databricks.yml | Bundle, Job tasks, dependencies, inputs, and deployment target | [Volume-to-extraction bundle](../assets/workflow/databricks.yml) |
| udp_workflow.yaml | Workflow title and description; identifies the workspace folder as a workflow | [Manifest](../assets/workflow/udp_workflow.yaml) |
| udp_workflow.schema.json | Format of the workflow manifest | [Manifest schema](../assets/workflow/udp_workflow.schema.json) |
| README.md | Summary, source, output tables, and links for users | [README template](../assets/workflow/README.md) |
| SPEC.md | Current business requirements and processing design | [SPEC template](../assets/workflow/SPEC.md) |
| AGENTS.md | Resource locations, decisions over time, and verification evidence for later agents | [Agent notes template](../assets/workflow/AGENTS.md) |

Copy the starting assets to the workflow root and adapt the bundle and Markdown
to the user's workload. Replace the illustrative workflow title. The bundle's
required variables must be set before validation. Add src/ only when a task
needs a source file; a workflow made entirely of AI Function tasks needs none.

## Manifest

Keep `udp_workflow.yaml` directly in the workflow folder. Give it
`schema_version: 1`, a title, and a useful description. Copy the supplied JSON
Schema unchanged alongside it and validate the manifest against that schema.
Preserve a manifest with an unrecognized schema version and ask how to proceed.

Additional manifest fields describe specific workflow features:

- `sample_tables`: fully qualified tables used for sample documents, when those
  tables exist. Do not invent a samples table just to populate the manifest.
- `routers`: class-routing metadata, when a classification/routing branch exists.
  Keep it aligned with the Job and its routed tables.
- `genie_code_thread_id`: maintained by Databricks. Preserve it when present;
  a third-party agent does not create a Genie Code conversation ID.

The manifest describes the workflow. Resource definitions, table destinations,
and task configuration belong in the bundle.

## Current design and history

Keep SPEC.md current as requirements are resolved. Record the use case, exact
source, document types, processing stages, extraction field map, destination
tables, validation rules, sample results, deployment target, and open decisions.
Distinguish user decisions from observations made from documents.

Keep dated changes, resource IDs, actual output table names, run/query IDs, and
validation results in AGENTS.md. Preserve useful notes when reopening a workflow.
README.md should describe the workflow as it exists now and link to its results.

## File changes

Use databricks.yml as the source of truth for bundle-managed resources and
redeploy changes through the bundle. If a SQL task or notebook is needed, put
its file in src/ and reference it from the task configuration. Use the
`databricks-jobs` skill for the relevant task type.

Keep the folder stable after creation so links and deployments continue to
refer to it. Files can be managed in the user's Git repository for review and
version history. A plain workspace folder does not provide Git history.
