---
name: lakeflow-unstructured
description: "Create, deploy, and update Document Intelligence workflow folders from existing Unity Catalog volume files or Delta tables. Use for local document-processing workflows with AI Function tasks and a handoff to Document Intelligence and Genie Code. Source ingestion and connector setup are outside scope."
compatibility: Requires a current Databricks CLI and a workspace with Document Intelligence, deployment history, and AI Function tasks available.
metadata:
  version: "0.0.1"
parent: databricks-core
---

# Lakeflow Unstructured

Create a local workflow folder that deploys a Lakeflow Job and opens in **Data
Ingestion > Document Intelligence**. Start with files already in a Unity Catalog
volume or content already in a Delta table. A volume can feed Document Parsing
directly; it does not need a new ingestion pipeline or bronze table.

This skill is experimental. Use the UI and Genie Code for evaluation, improving
extraction quality, and visual debugging.

## Companion skills

Use `databricks-core` first for CLI installation, authentication, and the user's
selected profile. Use `databricks-dabs` for bundle configuration and deployment,
`databricks-jobs` for task configuration, and `databricks-ai-functions` for direct
SQL syntax and extraction schemas. These stable skills are available through
`databricks aitools install`. Load them when needed; this skill supplies the
workflow-specific file and deployment conventions.

## Working with the user

Gather requirements through normal conversation. Reuse details already supplied
in the conversation or workflow files, and ask only for information that blocks
the next step. Group related missing details briefly and accept partial answers.
Inspect authorized sources and samples before asking the user to define a full
extraction schema. Present proposed fields, tasks, and unresolved business rules
together for review; retain confirmed choices and existing authorization.

Ask directly for paths, table or column names, and other text values. Use
multiple-choice questions only for meaningful decisions with distinct outcomes.
Keep instructions and commands in normal conversation, outside answer choices.
Do not direct the user to client-specific labels or option numbers to enter text.

Keep the selected workspace/profile during authentication recovery. If login
requires the user's browser or terminal, provide a copyable command, explain
where to run it, and wait for completion before verifying that same profile.
If access remains blocked, explain the blocker and continue only independent
local design work, marking assumptions that still need source verification.

Limit authentication diagnostics to profile names, workspace URLs, validation
results, and whether credential variables are present. Never print environment
dumps, credential files, or authentication output containing token values.

## Workflow

1. **Establish the starting point.** Identify the business goal and the user's
   selected workspace/profile. Reuse an existing source path or table when
   supplied. If the user needs help finding the source, use authorized read-only
   discovery in that workspace and present relevant accessible sources. For an
   existing workflow, read its manifest, SPEC.md, AGENTS.md, and bundle before
   changing it. Preserve the user's source, destinations, and existing assets.
2. **Design the document processing.** Read
   [Document processing](references/document-processing.md). Inspect a small
   representative sample when authorized. Reuse the user's extraction schema or
   propose typed fields with descriptions from the samples. Confirm business
   rules and handling of missing values with the user. Resolve the output
   catalog/schema as the design takes shape. Show the task chain and the planned
   input/output tables before configuring deployment.
3. **Author the workflow folder.** Read
   [Workflow folder](references/workflow-folder.md). Start from the bundled
   assets, write the current design to SPEC.md, and keep decisions and validation
   evidence current as the workflow changes. A plan-only request creates no
   workspace resources.
4. **Validate and deploy.** Read
   [Deploy and open](references/deploy-and-open.md). Validate the bundle and
   deploy the authorized development target. Publish the workflow files to the
   same workspace folder recorded by the deployment, with deployment history
   enabled from the first deploy.
5. **Verify and hand off.** Verify the deployed Job's settings and the workflow
   page's deployment association. When a test run is authorized, state how much
   input it will process, inspect task outputs and errors, and record the result.
   Return the workflow and Job links. Offer the UI/Genie Code handoff for
   evaluation and improvements before production use.

Honor authorization already given. Obtain missing design decisions before
implementing them, and get approval for production deployment, scheduling, or
replacing existing data or resources.

## Scope

- Build document-processing workflows from existing volumes or tables. Configure
  parsing and extraction as native AI Function tasks. Add classification only
  when the workload needs labels or different processing by document type.
- Keep source ingestion outside this workflow: reuse existing connections and
  sources. If documents are not yet accessible in a volume or table, explain the
  required starting point rather than creating connectors or ingestion pipelines.
- Perform functional checks on schemas, outputs, errors, and repeat runs. Run
  quality evaluations, hill climbing, and visual debugging in Document
  Intelligence with Genie Code.
- Report authoring, deployment, execution, and quality verification separately.
  A successful deploy does not establish extraction accuracy.
