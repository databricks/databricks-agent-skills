# <Workflow title>

<!-- Replace placeholders with confirmed requirements or observations. Keep open
decisions explicit, and remove sections that do not apply. Keep the current
design here and record its history in AGENTS.md. -->

## Use case

<Business result, who consumes the output, and what they use it for.>

## Existing input

<Exact volume directory or fully qualified Delta table and content column.
Document types, processing unit, stable identity, and expected input size.
Source access is already configured.>

## Processing design

<Task chain, dependencies, row meaning, and handling of unreadable documents.
Include a diagram showing inputs, processing tasks, and output tables.>

## Extraction schema

<The current AI Extract field map, each field's meaning, and extraction
instructions. Include classification labels only when required.>

## Inputs and outputs

| Role | Location | Contents and identity |
| --- | --- | --- |
| Input | <Existing volume or table> | <Documents, content column, keys> |
| Parsed output | <Resolved table, when parsing is needed> | <Parsed content and source identity> |
| Extracted output | <Resolved table> | <Extracted fields, errors, and source identity> |

## Validation

<Required fields, types, missing/conflicting-value handling, and business checks.
Sample inputs and observed results. Separate functional verification from
extraction-quality evaluation.>

## Deployment

<Workspace/profile, local folder, published workspace folder, bundle target,
run identity, and Job/workflow links. A schedule only when requested.>

## Quality review in the UI

<Sample or ground truth locations, fields needing evaluation, and questions to
continue with Genie Code in Document Intelligence.>

## Decisions and open questions

| Decision | Reason and source |
| --- | --- |
| <Confirmed choice or unresolved question> | <Who decided, or what still needs an answer> |
