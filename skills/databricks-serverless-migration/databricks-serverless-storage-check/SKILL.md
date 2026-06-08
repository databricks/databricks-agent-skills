---
name: databricks-serverless-storage-check
description: "Detect cross-task file-sharing antipatterns in Databricks serverless jobs (writes to /local_disk0, /tmp, or trustedTemp that are read by sibling or child tasks on potentially different compute nodes) and recommend UC Volumes or /Workspace for handoff. Use when a serverless job fails with `INTERNAL_ERROR: [Errno 13] Permission denied` on /local_disk0 paths, when parallel child notebooks fail intermittently, when reviewing a DAB job before deploying to serverless, or when the user mentions trustedTemp, fan-out, or cross-task file handoff. Complements databricks-serverless-migration (which covers single-notebook migration)."
compatibility: Requires databricks CLI (>= v0.292.0) for --job-id and --run-id modes; --notebook / --dir / --job-yaml modes have no external dependencies.
metadata:
  version: "0.2.0"
parent: databricks-serverless-migration
---

# Serverless Storage Check

**FIRST**: Use the parent `databricks-serverless-migration` skill for the overall classic-to-serverless migration workflow (Ingest → Analyze → Test → Validate), CLI auth (which it inherits from `databricks-core`), and per-task scratch guidance (`/local_disk0/tmp`). This skill is a niche sub-skill of that workflow — it focuses **only** on the cross-task handoff antipattern that the parent skill explicitly delegates here (see the Category B → DBFS-paths row in `databricks-serverless-migration/SKILL.md`).

This skill detects a specific class of serverless failure: **cross-task file handoffs through local disk**. On serverless compute, each task may run on a different node, so a path written by a parent task to `/local_disk0`, `/tmp`, or a `trustedTemp` directory is not guaranteed to be visible to a child task. The typical symptom is:

```
INTERNAL_ERROR: [Errno 13] Permission denied:
'/local_disk0/spark-<id>/trustedTemp-<id>/tmp<id>'
```

The fix is to move the handoff off local disk and onto durable, cross-node storage — UC Volumes (preferred) or `/Workspace` (fallback) — or replace the file handoff entirely with `dbutils.jobs.taskValues` for small payloads.

This skill ships an executable preflight scanner (`scripts/preflight.py`) that statically detects these antipatterns and emits remediation guidance. It is intentionally narrow: it does **not** try to fix `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT`, which is a separate, platform-side intermittent issue (see "What this skill does NOT cover" below).

## When to use this skill

Use this skill when any of these triggers appear:

- A serverless job fails with `INTERNAL_ERROR: [Errno 13] Permission denied` on `/local_disk0`, `/tmp`, or a path containing `trustedTemp`
- Parallel child notebooks (`dbutils.notebook.run`) fail intermittently while the same logic succeeds when run sequentially in a single notebook
- A DAB job is about to be deployed to serverless and has multiple `notebook_task` or `pipeline_task` tasks
- The user mentions "trustedTemp", "fan-out", "cross-task file sharing", or `/local_disk0`
- A new serverless job design needs a sanity check before first run

This skill is a **niche sub-skill** of [`databricks-serverless-migration`](../SKILL.md) — the parent owns single-notebook migration and explicitly recommends `/local_disk0/tmp` for per-task scratch (which is correct *inside* a task). This sub-skill picks up where the parent leaves off: anything that crosses a task boundary. The boundary between the two skills:

| Concern | Use skill |
|---------|-----------|
| Migrating one notebook from classic DBR to serverless | `databricks-serverless-migration` (parent) |
| Per-task scratch storage (intra-task) | `databricks-serverless-migration` (parent — recommends `/local_disk0/tmp`) |
| **Cross-task file handoff between parent/child notebooks or sibling tasks** | **this skill (sub-skill)** |
| Permission-denied on `/local_disk0` during a multi-task run | **this skill (sub-skill)** |

Always invoke the parent skill **first** for the overall migration plan, then return here to harden cross-task handoffs before deploying a multi-task serverless job.

## Quick start

Run the preflight scanner against any of: a single notebook, a directory, a DAB job YAML, a remote job, or a failed run.

```bash
# Single notebook
python3 scripts/preflight.py --notebook path/to/notebook.ipynb

# Recursive scan of a directory
python3 scripts/preflight.py --dir path/to/repo/

# A DAB job YAML (auto-resolves referenced notebooks)
python3 scripts/preflight.py --job-yaml resources/my_job.job.yml

# A remote job (pulls notebook source via databricks workspace export)
python3 scripts/preflight.py --job-id 123456789 --profile DEFAULT

# A failed run (classifies the error trace as fan-out vs env-sync)
python3 scripts/preflight.py --run-id 987654321 --profile DEFAULT

# Machine-readable output for CI gating
python3 scripts/preflight.py --dir . --json
```

## Interpreting the output

The scanner prints findings grouped by severity. Each finding includes the pattern ID, file, line, code snippet, and a recommended fix snippet.

| Severity | Meaning | Exit code |
|----------|---------|-----------|
| **Blocker** | Will fail on serverless. Must fix before deploy. | `2` |
| **Warning** | Likely to fail under parallel execution. Should fix. | `1` |
| **Info** | Awareness-only or escalation routing (e.g. env-sync error). | `0` |

Clean scans exit `0`. Use `--json` for CI: pipe to `jq` or fail builds when blockers are found.

## The core rule

The boundary between safe and unsafe local-disk use on serverless:

> **Local disk (`/local_disk0`, `/tmp`, `trustedTemp`) is per-task only.** Anything one task writes that another task reads MUST live on `/Volumes` or `/Workspace`.

This is verbatim from the BSI thread guidance: when the parent task writes to local disk and the child task tries to read it, the child may be on a different node and the file won't exist (or will hit `Permission denied`). See [`references/remediation-guide.md`](references/remediation-guide.md) for concrete before/after patterns.

## Pattern catalog (summary)

| ID | Severity | What it detects |
|----|----------|-----------------|
| `FANOUT001` | Blocker | Local-disk path written then passed to `dbutils.notebook.run`, `taskValues.set`, or job-task parameter |
| `FANOUT002` | Blocker | Child notebook reads from `/local_disk0` or `/tmp` via widget, parameter, or `taskValues.get` |
| `FANOUT003` | Warning | DAB job with multiple sibling tasks referencing the same local-disk path |
| `FANOUT004` | Warning | `pipeline_task` immediately downstream of a `notebook_task` that wrote to local temp |
| `FANOUT005` | Info | `dbutils.fs.cp` from local path to local path inside a multi-task job (heuristic) |
| `FANOUT006` | Blocker | Hardcoded path matching the BSI signature `/local_disk0/spark-*/trustedTemp/...` |
| `ENV001` | Info | Run output contains `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` — route to escalation |

Full rules, sample matches, and per-pattern fixes are in [`references/pattern-catalog.md`](references/pattern-catalog.md).

## Remediation summary

When the scanner flags a finding, prefer fixes in this order:

1. **UC Volumes** (preferred): `/Volumes/<catalog>/<schema>/<volume>/handoff/<run_id>/...`
   - Durable, cross-node, UC-governed, works for any file size
   - Requires `WRITE FILES` on the volume and a parent that creates the volume per run or per job

2. **`/Workspace`** (fallback): `/Workspace/Shared/<job_name>/handoff/...`
   - Durable and cross-node, no UC dependency
   - Best for smaller files; subject to workspace storage limits

3. **`dbutils.jobs.taskValues`** (small payloads only): no file at all
   - For scalars and small JSON (well under 48 KB total per run)
   - Replaces the file entirely — preferred when the handoff is just a parameter, config, or summary

4. **Keep `/local_disk0/tmp`** for **intra-task scratch only**. Never for cross-task.

Full before/after code is in [`references/remediation-guide.md`](references/remediation-guide.md).

## What this skill does NOT cover

The original BSI thread combined two distinct failures. This skill addresses only the storage one. The other failure, `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` / "Virtual environment changed while syncing", is a rare, platform-side issue that the Databricks team treats as an engineering escalation. The scanner detects it in `--run-id` mode and emits an `ENV001` info finding routing the user to support, but does not attempt to fix it.

If the scanner emits `ENV001`:

1. Open a Databricks engineering support ticket (use the `/jira-actions` skill or `/support-escalation` if available) with the run ID and error trace
2. As a temporary mitigation, reduce dependency setup during child notebook startup (move heavy `%pip install` to the parent or a job-level environment spec)
3. Add retries on the affected task — the error is usually transient

## Related skills

- [`databricks-serverless-migration`](../SKILL.md) — **parent skill**. Single-notebook classic-to-serverless migration and the overall Ingest → Analyze → Test → Validate lifecycle. **Always invoke first** if the workload hasn't been migrated yet — this sub-skill assumes you've already done the single-notebook port and are now hardening cross-task handoffs.
- [`databricks-dabs`](../../databricks-dabs/SKILL.md) — DAB structure and resource definitions. Use when authoring or fixing the `job.yml` flagged by `FANOUT003` or `FANOUT004`.
- [`databricks-jobs`](../../databricks-jobs/SKILL.md) — Lakeflow Jobs orchestration. Use when restructuring task dependencies to avoid the fan-out antipattern.
- [`databricks-core`](../../databricks-core/SKILL.md) — grandparent skill, inherited via `databricks-serverless-migration`, for CLI auth and profile selection.

## Reference docs

- [Pattern catalog](references/pattern-catalog.md) — all detection rules with examples
- [Remediation guide](references/remediation-guide.md) — before/after code for Volumes, Workspace, and taskValues handoffs

## External documentation

- [Serverless compute limitations](https://docs.databricks.com/en/compute/serverless/limitations) — official local-disk scoping rules
- [Unity Catalog volumes](https://docs.databricks.com/en/connect/unity-catalog/volumes.html) — the preferred handoff target
- [Workspace files](https://docs.databricks.com/en/files/workspace.html) — the fallback handoff target
- [`dbutils.jobs.taskValues`](https://docs.databricks.com/en/dev-tools/databricks-utils.html#task-values-utility-dbutilsjobstaskvalues) — for non-file handoffs
