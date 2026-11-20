# Continuous Pipelines (schedule-based)

How to make a pipeline run continuously — always-on, processing data as it arrives. This is a
run-mode change: no dataset code changes, and identical for Python and SQL pipelines.

## The rule

**To make a pipeline continuous, create a continuous schedule on it** (a job with a continuous trigger). Do NOT edit the pipeline settings with `continuous: true`; the spec's `continuous` field is the legacy mechanism.

The spec stays `continuous: false` (triggered); the schedule supplies the continuous behavior.

## Both mechanisms exist — check before changing mode

Existing pipelines may still use the legacy spec field, so **`continuous: true` is something you will
encounter and it still works.** Never assume which mechanism a pipeline uses: read the pipeline details first, then act on what you find.

To make a pipeline triggered (stop continuous execution), the fix depends on which mechanism is
driving it:

- **`continuous: true` in the spec** (legacy) — edit the pipeline settings with `continuous: false`.
- **`continuous: false` but still running continuously** — a continuous schedule is driving it, so
  **pause** that schedule (do NOT delete it), **then cancel the job run it already started**. Pausing
  alone does not stop the in-flight run, so the current update keeps going. Editing the pipeline settings
  cannot stop either, and re-setting `continuous: false` does nothing.

Confirm which case you are in by reading the latest update: `mode: "CONTINUOUS"` on a pipeline whose spec is `continuous: false` means a
continuous schedule is driving it, and `cause: "JOB_TASK"` confirms a job started that update.

## Creating a continuous schedule

Create a job whose task is the pipeline (a `pipeline_task` with its `pipeline_id`) and whose job settings
have a `continuous` trigger. In a bundle project, add the job to the bundle.

If you cannot create the job (for example, no permission), tell the user to add a schedule to the
pipeline with the continuous trigger type. Do not fall back to
editing the pipeline settings with `continuous: true`.

## Constraints

- **To stop continuous execution, pause the schedule and cancel its active run — never delete the
  schedule.** Pausing stops *future* runs; on its own it leaves the in-flight run going, so cancel
  that run too (or cancel all runs on the job when you don't have a run id). Pausing is reversible and
  keeps the schedule's configuration — only suggest deleting one if the user explicitly asks.
- **One continuous schedule per pipeline.** A pipeline with a continuous schedule should not take
  additional schedules. To add a *different* schedule the user can change the existing job's trigger
  type or delete it — state the options and let them decide, and do not delete it on their behalf.
  Adding a continuous schedule to a pipeline that already has other schedules is technically allowed
  but discouraged.
- **An active update does not block creating a schedule, but the runs it starts will fail.** A pipeline
  runs one update at a time, so a continuous job will keep starting and failing runs for as long as the
  pre-existing update is active — it is not just the first run. Suggest stopping the running update
  first; creating the schedule itself still succeeds.
- **Maintenance window (optional).** The continuous schedule (the wrapping job) can carry a weekly
  maintenance window — the window when Databricks may restart the job for maintenance. It has three
  required fields: `start_hour` (0–23), `day_of_week` (`MONDAY`…`SUNDAY`), and `timezone_id` (IANA,
  e.g. `America/New_York`). Set it on the schedule's job, not in the
  pipeline spec. If the user asks for one but leaves any field unspecified, ask for the missing
  value(s) rather than guessing.


