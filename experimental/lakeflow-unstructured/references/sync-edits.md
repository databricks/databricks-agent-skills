# Synchronize workflow edits

Local files and the workspace folder are copies of the same workflow. A bundle
deploy publishes local files and resource definitions. Edits made in Document
Intelligence, Genie Code, or the Job editor need to be reconciled before the
next local deployment. Use workspace file and resource APIs through the CLI to
inspect them; a browser session is not required for this comparison.

## When to check

| Event | Check |
| --- | --- |
| Reopen an existing workflow | Compare local files, workspace files, and deployed settings before editing. |
| Return from UI or Genie Code work | Retrieve the current files and settings before continuing locally. |
| Immediately before every deployment | Repeat the comparison to catch intervening edits, then review the deployment plan. |
| Before an authorized run | Check the deployed configuration and workspace source files against the design the user intends to run. |
| After deployment | Verify the published files and read back resource settings before recording synchronization. |

Use these checkpoints rather than background polling. The skill does not run
while the agent is closed. Reuse authorization already given for the workflow;
a synchronization check does not authorize deploying or running it.

## Identify and retrieve the workflow

Reuse the recorded workspace URL/profile, workflow folder path and object ID,
bundle target, and resource IDs. Keep comparisons specific to that workspace
and target. If the folder's identity differs from the recorded one, resolve
which workflow the user intends before publishing into it.

Replace placeholders below. Export into a new local snapshot directory outside
the local workflow root, so the export cannot overwrite local edits or become
part of a subsequent bundle upload:

```bash
databricks workspace get-status "<workspace-workflow-path>" --profile <profile> --output json
databricks workspace export-dir "<workspace-workflow-path>" "<new-local-snapshot-directory>/files" --profile <profile>
databricks jobs get <job-id> --profile <profile> --output json
```

Save the relevant Job settings alongside the exported files. For other
bundle-managed resources, such as routing pipelines, read their current
settings through the corresponding companion skill. Complete the reads before
treating the snapshot as current; a failed or partial read is not evidence that
a file or resource was deleted. `workspace get-status` identifies the folder;
it does not establish whether its contents match the local files.

Include the manifest, bundle and included resource YAML, SPEC.md, AGENTS.md,
README.md, and source files used by the workflow. Review added, deleted, and
renamed files as well as changed content. Notebook exports can add language
extensions; map them to the source paths referenced by the bundle before
comparing. Preserve workflow files added in the UI when they are part of the
accepted design.

## Compare with the last synchronized baseline

After a verified deployment, retain snapshots of the local source, exported
workspace files, and relevant deployed settings as the baseline for the next
comparison. Keep these snapshots outside the workflow root and source control,
keyed by workspace, folder ID, and target. Record the verification time and
accepted changes in AGENTS.md; keep the local snapshot location in local notes.
Credentials and bundle deployment state are not synchronization content.

Compare each side to its saved representation. File contents or content hashes
show changes; timestamps alone cannot decide which edit to keep. Use the saved
contents to merge edits rather than treating the most recent copy as the winner.

| Changes since the baseline | Action |
| --- | --- |
| Local files only | Keep the local edits and validate/plan the authorized deployment. |
| Workspace files only | Bring the workspace changes into the local project, preserving their source paths and bundle references. |
| Both copies changed | Merge compatible edits. Show conflicting edits and obtain the user's decision before overwriting either version. |
| Deployed settings changed | Reconcile intended resource edits into the local bundle, even if the workspace files are unchanged. |

If no trustworthy baseline exists, retrieve both copies, show meaningful
differences, and resolve which changes to retain before establishing one.
Equal file copies can be recorded as matching, but still inspect deployed
settings. Do not invent a history or silently choose a winner for differences.

Compare configurable resource settings with their last verified read-back and
the resolved configuration for the selected target. Account for development
mode defaults, resolved paths, and server-generated fields. A Job editor change
may not update the workspace's databricks.yml. Translate accepted settings back
into bundle source; do not replace the bundle with raw Job JSON or copy
deployment-resolved IDs into source references. Preserve local variables and
target-specific configuration, applying accepted changes to the correct
variable or target override so an older local override does not mask them.

For example, if Genie Code adds an extraction field while the local project
changes its description, merge both changes when compatible. If both sides
change that field's type differently, present the conflict before deployment.

## Validate, publish, and record

Update SPEC.md and AGENTS.md to reflect accepted changes, then follow
[Deploy and open](deploy-and-open.md) to validate, plan, and deploy within the
authorized scope. Review resource replacements and output destinations before
publishing. Immediately before deploy, recheck files and settings that may have
changed during reconciliation. Coordinate with anyone actively editing the
workflow; these read checks do not lock workspace files or Job settings.

Read back the published files and deployed settings and verify they match the
reconciled configuration. Refresh the baseline only for verified matching
content. Keep pending local changes and unresolved differences separate;
failed deployment or incomplete verification does not establish synchronization.
When only importing workspace changes, verify the resulting local files match
that snapshot before advancing their baseline, and keep any resource mismatch
open until resolved. Continue to use the same folder and bundle deployment.

Before a run, explain any difference between the current local design and the
deployed version. Run the version covered by the user's authorization; deploy
pending edits only when deployment is also authorized. Report unavailable
comparisons instead of claiming the workflow is synchronized.
