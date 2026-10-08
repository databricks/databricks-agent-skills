---
name: databricks-serverless
description: "Serverless compute for Databricks jobs, Lakeflow pipelines and Declarative Automation Bundles (DABs), with STANDARD or PERFORMANCE_OPTIMIZED and classic only where serverless cannot run the workload. Use when creating, deploying, scheduling or editing a job or pipeline, or deciding its compute. Invoke BEFORE writing a job spec. For migrating existing classic workloads, use databricks-serverless-migration."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.3.2"
parent: databricks-core
---

# Deploying Databricks jobs and pipelines on serverless

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication and profile selection.

This skill decides compute. Where another skill or example (for example `databricks-jobs`) shows
cluster configuration, follow this skill instead.

Serverless is the default compute for every job, pipeline and bundle you create. If the user
explicitly asks for a cluster, do what they ask and mention the serverless option in one line.
When editing an existing job, keep its compute unless the user asks to change it; tasks you add
follow this skill.

## 1. Serverless or classic

Use classic compute only for:

- R code, or Scala in notebook cells (`%scala`): serverless notebooks run Python and SQL only;
- custom Docker images;
- OS packages (`apt-get`) or native libraries with no pip equivalent;
- custom Spark data source JARs;
- a stated hard requirement for an instance type or Databricks Runtime version;
- an explicit user request;
- existing code over the budget in section 5;
- a workspace without serverless: if creating or running the job fails because serverless is not
  available there, put the whole job on classic and say so.

Then give only the blocked task a cluster (one small `job_clusters` entry with the latest LTS
runtime and `autoscale: {min_workers: 1, max_workers: 4}`), keep every other task serverless, and
state the blocker in one line. For a blocked pipeline, give the pipeline a `clusters` block instead
of `serverless: true`.

Not reasons for classic: Scala or Java in a JAR task (JAR tasks run on serverless), GPUs (serverless
GPU), large data, long runtimes, Kafka, cost (serverless STANDARD is on par with or cheaper than
on-demand classic in most cases), or habit.

## 2. Put every task on serverless

- **New jobs:** leave out `new_cluster`, `job_clusters`, `job_cluster_key`, `existing_cluster_id`,
  `instance_pool_id`, `node_type_id`, `num_workers`, `autoscale`, `spark_version`. A task without a
  cluster runs on serverless. In an existing job, keep the cluster settings it has.
- **Notebook tasks** need nothing else. **Python script, wheel and JAR tasks** take their libraries
  from a job-level environment. Use the latest environment version the workspace offers, as a
  quoted string:
  ```yaml
  environments:
    - environment_key: default
      spec:
        environment_version: "4"                # example; use the latest
        dependencies: ["requests==2.32.3"]   # pin versions; JARs go in java_dependencies
  tasks:
    - task_key: main
      spark_python_task: {python_file: /Workspace/.../main.py}
      environment_key: default
  ```
- **SQL tasks:** a serverless SQL warehouse. **Pipelines:** `serverless: true`, no `clusters` block.
- **Streaming:** `.trigger(availableNow=True)`, the trigger serverless supports (no `processingTime`
  or `continuous` triggers). For always-on processing, run that stream in a continuous job
  (`continuous: {pause_status: UNPAUSED}`), which starts the next run as soon as one finishes, or use
  a continuous pipeline.
- **Tag every job you create** for resource tracking, as other Databricks skills do: job-level
  `tags: {"aidevkit_project": "ai-dev-kit"}`. Keep tags the user already has.

## 3. Choose the performance mode

Set the job-level `performance_target`:

- **`STANDARD`** when nothing is time-critical and cost matters more than speed: scheduled batch and
  ETL, nightly or weekly runs, or any job where the user states no latency need. Runs start within
  minutes instead of seconds and cost less. This is the default choice.
- **`PERFORMANCE_OPTIMIZED`** only when the user names an SLA or a deadline that is tight relative
  to the runtime, a person waits on the result, or the job runs every 30 minutes or more often.

`performance_target` applies to the whole job, notebook tasks included (only interactive notebooks
always run performance-optimized). Say which mode you chose and why in one line, e.g. "STANDARD:
nightly batch, no deadline."
Serverless GPU tasks ignore `performance_target`.

Pipelines have no `performance_target` of their own. To schedule a pipeline, trigger it from a job
with a `pipeline_task` and set the mode on that job; the job's mode applies to the pipeline update.
A continuous pipeline runs in STANDARD only when a continuous job runs it.

## 4. Code you write runs on serverless from the start

Serverless reads Unity Catalog tables, `/Volumes/...` paths, cloud paths behind a Unity Catalog
external location, and the sample data under `dbfs:/databricks-datasets/`. It cannot read DBFS
mounts (`dbfs:/mnt/...`) or other DBFS root paths; only those count as a DBFS blocker.

DataFrame and SQL APIs only (no RDDs, `sc.*`, `spark.sparkContext`); Unity Catalog three-part table
names; `/Volumes/...` paths instead of DBFS mounts (`dbfs:/mnt/...`); `availableNow` streaming
triggers; no `.cache()` or `.persist()`; no `spark.conf.set` for executor, driver or memory
settings; pinned dependencies in the environment, never init scripts.

## 5. Existing code: a quick check, not a migration

The user is waiting for the deployment. Spend one short pass, then deploy.

1. **Scan only the files the job runs** (a text search such as `grep` or `rg`; do not read the whole
   repo) for: `sc.`, `sparkContext`,
   `.rdd`, `parallelize`, `mapPartitions`, `reduceByKey`, `groupByKey`, `dbfs:/`, `/dbfs/`,
   `dbutils.fs.mount`, `.cache(`, `.persist(`, `spark.conf.set`, `processingTime`, `continuous=`,
   `writeStream`, `hive_metastore.`, `GLOBAL TEMP`, `hivevar`, `init_scripts`, `apt-get`, `docker`,
   and other languages: `%scala` or `%r` as the whole magic (`# MAGIC %r`, not `%run`), `.r` files
   and R notebooks, `SparkR` and `sparklyr`. R and Scala cells go to classic (section 1).
2. **Minor blockers: fix them and deploy on serverless** if every fix is mechanical and local, keeps
   the logic, needs no new infrastructure, and there are about 5 small edits or fewer in total:
   - delete `.cache()`, `.persist()`, `.unpersist()`, `setLogLevel`, executor/driver/AQE `spark.conf.set` lines
   - move `pip install`s or `requirements.txt` into the environment, pinned
   - add `.trigger(availableNow=True)` to a stream that sets no trigger, in a job that runs on a
     schedule anyway (a stream with a `processingTime` or `continuous` trigger is a step 4 blocker)
   - replace a `dbfs:/mnt/...` path with a `/Volumes/...` path only when that volume's storage
     location is the mount's source, so the job reads the same data; a volume with a similar name is
     not enough. Otherwise the mount is a step 4 blocker.
   - `CREATE GLOBAL TEMP VIEW` becomes `CREATE TEMP VIEW`, and its `global_temp.<view>` reads become
     `<view>`, when the same file creates and reads the view (serverless has no global temp views); a
     global temp view that another task or notebook reads is a step 4 blocker
   - add the catalog to a two-part table name only when you know which Unity Catalog catalog holds the
     table (for example the job's default catalog); a table in `hive_metastore` is a step 4 blocker

   List every edit you made in your reply.
3. **RDD or SparkContext code: translate it to DataFrames and deploy on serverless** only if all of
   these hold:
   - it is one file of about 200 lines or fewer;
   - the change is a pure API translation: the same logic, expressed with DataFrame or SQL;
   - every input path, table, output table and parameter stays exactly as it was. Never swap in
     another dataset, even a sample one;
   - every input is already readable on serverless (section 4: a Unity Catalog table, an existing
     `/Volumes/...` path, a cloud path behind an external location, or `dbfs:/databricks-datasets/`),
     so nothing new has to be set up.

   Save the original next to it as `<name>.classic.py` and point the job at the translated file.
   Tell the user that the translation has not been run yet and suggest one test run that compares
   the output with the classic version.
4. **Anything bigger: do not rewrite.** Put that task on classic now (section 1), keep the other
   tasks serverless, and end with: "Kept <task> on classic because <blocker>. To move it to
   serverless, use the databricks-serverless-migration skill." Bigger means: RDD code that fails any
   condition in step 3 (for example it reads a DBFS mount), mounts with no volume on the same
   storage, Hive Metastore to Unity Catalog, recompiling a JAR, networking changes, changing what a
   stream does (an always-on `processingTime` or `continuous` stream), or more than about 5 edits
   besides a step 3 translation.

Do not stop to ask whether to migrate. Deploy, then report what you did.

## Common Issues

| Issue | Solution |
|-------|----------|
| `Libraries field is not supported for serverless task` | Move libraries into `environments[].spec.dependencies` (JARs: `java_dependencies`) and set `environment_key` on the task |
| Serverless job starts too slowly | `performance_target: PERFORMANCE_OPTIMIZED`, only if the user needs fast starts (section 3) |
| `Only remote Spark sessions ... are supported` or another RDD error | RDD/SparkContext code: section 5, step 3 or 4 |
| `[PATH_NOT_FOUND]` or no access on `dbfs:/mnt/...` | DBFS mounts do not work on serverless: use a volume on the same storage (section 5, step 2), otherwise step 4 |
| Serverless is not enabled or not available in the workspace | Put the job on classic and tell the user (section 1) |
| A sibling skill's example uses `job_clusters` for a new job | Leave the cluster block out; this skill decides compute. Existing jobs keep their compute |

## Related Skills

- **databricks-core** - CLI basics, authentication, profiles
- **databricks-jobs** - job structure, task types, triggers, notifications
- **databricks-pipelines** - Lakeflow Spark Declarative Pipelines
- **databricks-serverless-migration** - migrating existing classic workloads to serverless

## Documentation

- [Serverless compute for jobs](https://docs.databricks.com/jobs/run-serverless-jobs)
- [Serverless compute limitations](https://docs.databricks.com/compute/serverless/limitations)
- [Serverless dependencies (environments)](https://docs.databricks.com/compute/serverless/dependencies)
- [Serverless pipelines](https://docs.databricks.com/ldp/serverless)
