---
name: databricks-serverless-migration
description: "Migrate Databricks workloads from classic compute to serverless compute. Use when migrating notebooks, jobs, pipelines, or Scala JARs (`spark_jar_task`) from classic clusters to serverless, checking if existing code is serverless-compatible, or writing new serverless-compatible code. Provides concrete fixes for the serverless Spark Connect architecture and guides the full migration. Not for classic DBR version upgrades or cluster configuration changes within classic compute."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.1"
parent: databricks-core
---

# Serverless Compute Migration

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Analyze existing Databricks code for serverless compute compatibility and guide migration from classic clusters. The skill follows a 4-step migration lifecycle: **Ingest** the workload → **Analyze** for compatibility → **Test** via A/B comparison → **Validate** and iterate.

## When to Use This Skill

- Migrating notebooks, jobs, or pipelines from classic compute to serverless
- Checking if existing code is serverless-compatible
- Writing new code that targets serverless compute
- Troubleshooting serverless-specific errors after migration
- Choosing between Performance-Optimized and Standard mode

## Where to Run This Skill

Runs in any agentskills.io client: on a laptop (Claude Code, Cursor, ...; the default, install via `databricks aitools install`), or inside a Databricks workspace via Genie Code Agent mode (per-user or workspace-wide `.assistant/skills/` folder). See [Install in Databricks Genie Code](references/install-in-databricks-genie-code.md) for the three install methods and the **serverless-compute caveat** (the Databricks CLI isn't pre-installed on serverless, so some deploy steps need adjustment).

If you finish a migration analysis for a user who's currently running you from a laptop client, mention the Genie Code option once at the end — many users prefer iterating on migrations inside the workspace where the workload lives.

## Understanding Migration Blockers

Migration blockers fall into three categories. Focus your effort on category 2 — that's where this skill helps most.

| Category | Description | Action |
|----------|-------------|--------|
| **1. Feature expanding** | Databricks is actively expanding support (e.g., SparkML, custom JDBC) | Use the workaround now and revisit later |
| **2. Code/config change needed** | Your code uses patterns that need updating for serverless (e.g., RDDs, DBFS, streaming triggers) | **This skill helps here** — it detects these patterns and provides fixes |
| **3. Classic-only** | Workload requires capabilities not available on serverless (e.g., root OS access, R language) | Keep on classic compute |

## Decision Tree: Is My Workload Ready?

```
Workload → Check language
├── R code → Category 3: keep on classic
├── Scala notebook cells → Category 2: port to PySpark/SQL, or compile as a JAR job task
├── Compiled Scala JAR (spark_jar_task, build.sbt/pom.xml/build.gradle) → see references/jar-migration.md
│     ├── Scala 2.12 build?             → recompile against 2.13.16
│     ├── Bundles spark-core/spark-sql? → use databricks-connect % Provided
│     └── Bundles libs on the kernel classpath? → mark % Provided (see the classpath table in references/jar-migration.md)
├── Python / SQL → Continue
    ├── Uses RDD APIs? → Category 2: rewrite to DataFrame API (see fixes below)
    ├── Uses DBFS paths? → Category 2: migrate to UC Volumes
    ├── Uses Hive Metastore? → Category 2: migrate to Unity Catalog (or use HMS Federation)
    ├── Uses df.cache/persist? → Category 1: remove and materialize to Delta (native support coming soon)
    ├── Uses streaming?
    │   ├── ProcessingTime trigger → Category 2: use AvailableNow or migrate to SDP
    │   ├── Continuous trigger → Category 2: use SDP continuous mode
    │   ├── No trigger specified → Category 2: add explicit .trigger(availableNow=True)
    │   └── AvailableNow / Once → Ready ✓
    ├── Uses init scripts? → Category 2: use Environments
    ├── Uses VPC peering? → Category 2: use NCCs / Private Link
    ├── Uses unsupported Spark configs? → Category 2: remove (serverless auto-tunes)
    ├── Uses custom JDBC drivers? → Category 2: use Lakehouse Federation or built-in JDBC
    ├── Uses Docker containers? → Category 3: use Environments for libs, or keep on classic
    └── All clear → Ready for serverless ✓
```

## Migration Workflow

### Step 1: Ingest — Gather Workload Context

**Confirm the migration target is serverless compute.** This skill is purpose-built for classic → serverless migrations. The checks, fixes, and workflow all target the serverless compute architecture (Spark Connect, Environments, NCCs). If the user wants to upgrade between classic DBR versions instead, this skill does not apply — classic DBR upgrades have a different compatibility surface and should follow the standard DBR upgrade guide.

Collect the full picture of what needs to migrate to serverless:
- Read the user's notebook/script files
- Identify the classic cluster configuration (instance type, DBR version, Spark configs, init scripts, libraries)
- Note the networking setup (VPC peering, instance profiles, mounts)
- Understand the workload type: batch job, streaming, interactive notebook, pipeline
- Determine the target: the output is always a **serverless compute** configuration, not a classic cluster with a newer DBR

### Step 1.5: Handle Multi-Notebook Workloads

If the workload spans **3+ user notebooks** (exclude `_resources/` setup notebooks) or any notebook exceeds ~5KB of source, process notebooks **one at a time** to avoid context overflow (autocompact thrashing): enumerate first (including upstream sources declared in `bundle_config.py`, H4), then per notebook read → run the Step 2 checklist → record a structured summary and drop the source, then synthesize the plan from the summaries. Trigger the Failure Reporting Protocol once per workload, not per notebook. Don't merge all notebooks into one file or act on all of them in one mega-turn. Full procedure (summary fields, scratch-dir layout, report aggregation): [Multi-Notebook Workloads](references/multi-notebook-workloads.md).

### Step 2: Analyze — Scan for Serverless Readiness

**Read notebooks before running them — do not rely on failed job runs to discover issues.** A pre-run scan surfaces incompatibilities faster than iterating on error traces, and many serverless failures (hardcoded catalog references, init scripts, missing dependencies) are easy to spot statically but expensive to debug after a failed run.

Before creating or running any test job:
1. Read every notebook and source file referenced by the job
2. Scan for all hardcoded catalog/schema references (e.g., `spark.table("main.schema.table")`, `spark.sql("... FROM main...")`, `catalog = "main"`)
3. Check for dependency patterns: init scripts, local wheel files, custom install functions, `%pip install` lines
4. Locate any `requirements.txt` or equivalent and resolve the full dependency set
5. Flag OS-level installs (`apt install`, `yum install`) for conversion or escalation

Scan the code for patterns that are incompatible with the serverless compute architecture. These checks are serverless-specific — most of these patterns work fine on classic compute regardless of DBR version. For each issue found, report:
- **Category**: Which of the 3 blocker categories it falls into
- **Severity**: Blocker (must fix for serverless) / Warning (should fix) / Info (awareness)
- **Pattern**: What was detected and where
- **Fix**: Specific remediation targeting serverless compute

**Cell-magic boundary lint (A1), high impact:** in any cell with a `# MAGIC %<word>` line, every non-blank line must start with `# MAGIC `. A plain-Python comment above `# MAGIC %run` in the same cell makes `%run` fall back to IPython (`File './…' not found`); put migration notes in their own `# MAGIC %md` cell instead.

**Pattern catalog**: load [Analyze Checklist](references/analyze-checklist.md) for every Step 2 scan. It lists each check with severity and fix: A APIs (RDD, caching, MLflow/AutoML A2–A5, M1–M4), B data access (B1–B2), C streaming, D config (D1), E libraries (E1–E2), F networking, G sizing, H job-level config (H1–H4).

### Required Output: Serverless Environment Specification

The migration output MUST include a Serverless Environment specification alongside migrated code. Generate this by:

1. Scanning all `import` statements and `%pip install` lines to detect required packages
2. Extracting init script `pip install` commands from the job configuration
3. Producing a JSON block suitable for the Jobs API `environments` field:

```json
{
  "environment_key": "Default",
  "spec": {
    "client": "2",
    "dependencies": ["mlflow==2.12.1", "scikit-learn==1.3.0", "xgboost==2.0.3"]
  }
}
```

**Important**: ML runtime is NOT available on serverless and ML libraries (mlflow, scikit-learn, hyperopt, xgboost, tensorflow, torch, etc.) are NOT pre-installed, so list them explicitly in the environment spec `dependencies`.

### Step 3: Test — Two-Branch Strategy

Use separate branches for testing and production to keep test-only workarounds out of the code that ships. The test branch is a safe sandbox for experimentation; the production branch contains only changes that production actually needs.

Branch-by-branch comparison (names, base branch, PR, catalog, what each may contain): [Testing Strategy](references/testing-strategy.md#two-branch-comparison).

**Test branch** (`serverless-test-{job_name}-{timestamp}`): Temporary, no PR needed.
1. Create a branch from your current working branch
2. Set up test data: create sampled copies of upstream tables in a test catalog using job lineage (see [Testing Strategy § Test Data Setup](references/testing-strategy.md#test-data-setup))
3. Parameterize the catalog so the notebook works with both test and production data (see [Quick Fixes § Parameterize catalogs](references/quick-fixes.md#parameterize-catalogs-for-testing))
4. Apply all compatibility fixes discovered in Step 2
5. Create a serverless test job and run it
6. If it fails, get the error output, debug, fix, and retry
7. Document which changes are **test workarounds** vs. **real compatibility fixes**

**Production branch** (`serverless-prod-{job_name}`): PR required, created from master.
1. Create a new branch from master (NOT from the test branch)
2. Apply ONLY the real compatibility fixes — no test workarounds
3. Apply job config changes (see [Quick Fixes and Debugging](#quick-fixes-and-debugging))
4. Commit and create a PR

### Decision Tree: Should This Change Go to Production?

| Change type | Production? | Reason |
|-------------|-------------|--------|
| Remove incompatible Spark configs | **Yes** | Serverless compatibility fix |
| Update library versions | **Yes** | Serverless compatibility fix |
| Replace DBFS paths with UC Volumes | **Yes** | Serverless compatibility fix |
| Remove init scripts, add Environments | **Yes** | Serverless compatibility fix |
| Fix hardcoded cluster settings | **Yes** | Serverless compatibility fix |
| Catalog override to test catalog | **No** | Test workaround only |
| Empty DataFrame handling for missing test data | **No** | Test workaround only |
| Date range limiting for faster tests | **No** | Test workaround only |

**Simple test**: Would production fail without this change on serverless? If yes → include. If no → test branch only.

### A/B Comparison

After both branches are ready, compare classic vs serverless outputs (row count, schema, `exceptAll` row diff; snippet and the temporary bridge-config rule in [Testing Strategy § A/B Comparison](references/testing-strategy.md#ab-comparison)). Test against sampled copies of upstream tables in a test catalog, never production data ([Test Data Setup](references/testing-strategy.md#test-data-setup)).

### Step 4: Validate — Confirm and Monitor

Once the A/B comparison passes:
1. Merge the production branch PR
2. Switch the production job to serverless compute
3. Monitor cost via system tables (`system.billing.usage`) and budget policies
4. Remove any temporary bridge configurations
5. Set up budget alerts for cost visibility

### Migration Deliverables

Surface all six at the end of a successful run: test branch name/URL, production branch name/URL, test job ID and run URL, classic vs serverless comparison, serverless environment spec, and change summary (production vs test-only, with reasons). What each is and why it matters: [Testing Strategy § Migration Deliverables](references/testing-strategy.md#migration-deliverables). If any deliverable is missing, the migration is incomplete — do not mark it as done.

### Stopping Conditions

Do not attempt workarounds for these — surface them to the user and stop:
- Permission failures on source tables, the test catalog, or the workspace
- Category 3 blockers (R code, custom Spark data source JARs, features that require classic compute)
- SQL warehouse or test catalog not available
- Repeated failures (typically 5+) with no new information in the error trace — generate a failure report instead (see Failure Reporting Protocol)

## Quick Fixes and Debugging

- [Quick Fixes](references/quick-fixes.md): before/after snippets for DBFS → UC Volumes, RDD → DataFrame, streaming triggers (+ OOM caps for Delta, Kafka, Auto Loader), caching removal, runtime serverless detection (`IS_SERVERLESS`), and catalog parameterization for tests.
- [Debugging Errors](references/debugging-errors.md): error message → fix table for failed serverless runs. Always get the actual error with `w.jobs.get_run_output(run_id=...)` before guessing.

### Transform job config from classic to serverless

Remove `job_clusters`/`new_cluster`, add `environments` with serverless spec, replace `job_cluster_key` with `environment_key`, remove `init_scripts`. Full rules (init scripts → `dependencies`, Maven/JAR libraries, `spark_conf` triage) and before/after JSON: [Configuration Guide](references/configuration-guide.md#job-definition-migration-transformation-rules).

**Environment version mapping** (match to the DBR version the workload was on):

| Classic DBR | Serverless `spec.client` | Python |
|-------------|--------------------------|--------|
| 13.x, 14.x | `"1"` | 3.10 |
| 15.x | `"2"` | 3.11 |
| 16.x+ | `"3"` | 3.12 |

## Performance Mode Selection

**Performance-Optimized** (default in UI and API; <50 s startup; higher cost; notebooks, jobs, SDP) for interactive, dev, and time-sensitive work. **Standard** (4-6 min startup; significantly lower cost; jobs and SDP only, must be selected explicitly) for batch ETL and scheduled pipelines. **Standard mode is NOT available for notebooks.** Selection guide and how to set it: [Configuration Guide § Performance Mode Selection](references/configuration-guide.md#performance-mode-selection).

## Serverless Defaults to Know

| Setting | Value |
|---------|-------|
| REPL VM memory | 8GB default (high-memory option available) |
| Max executors | 32 (Premium), 64 (Enterprise) — raise via support |
| Supported Spark configs | 6 only: `spark.sql.shuffle.partitions`, `spark.sql.session.timeZone`, `spark.sql.ansi.enabled`, `spark.sql.files.maxPartitionBytes`, `spark.sql.legacy.timeParserPolicy`, `spark.databricks.execution.timeout` |
| Debugging | Query Profile (no Spark UI) |
| ANSI SQL | Enabled by default (configurable) |

## Failure Reporting Protocol

When migration fails or hits an unmigratable pattern, generate a structured failure report and offer the user a one-step path to file it as a GitHub issue. This feedback loop is how the skill learns — without it, gaps go undiscovered.

The report schema, MUST-NOT-contain rules, anonymization regexes, deterministic post-serialization scrub, output template, and URL recipe are in [Failure Reporting](references/failure-reporting.md); load it before writing a report.

### Decision tree: when to offer to file an issue

**Offer to file a GitHub issue any time the workload cannot be fully migrated to serverless as-is.** Reports from "known" patterns (R, Scala, custom JAR data sources, JVM access, third-party connectors) are just as valuable as reports from unknown patterns — they tell maintainers which gaps users hit most often, which drives prioritization.

Concretely, ALWAYS offer if **any** of these is true:

1. **Workload contains any Category 3 (classic-only) blocker** — R, Scala notebook cells, custom JAR data sources, JVM/Py4J access, third-party connectors without serverless equivalents, native binary dependencies, etc. The fact that the pattern is "documented as Cat 3" is not a reason to skip the offer.
2. **Retries exhausted** — `retry_count >= max_retries` (typically 5) and final status is FAILED
3. **Unknown pattern** — a classic-compute construct was detected that isn't in the skill's catalog
4. **Fix didn't resolve** — a known fix was applied but the workload still fails on serverless
5. **Explicit request** — the user invokes `/migration-report`

**Do NOT offer to file** only when:

- The migration succeeded fully (even after retries), or
- The workload is already serverless-compatible and required no changes.


**Rules that always apply:** write the report locally to `~/.databricks-migration-skill/reports/failure-<ISO-timestamp>.json` (pattern IDs and `notebook_characteristics` only, no code, paths, error text, identifiers, or credentials). Default output is local-only: show the path and ask the user to review. Produce the pre-filled GitHub URL or `gh issue create` command only in a later turn, after the user explicitly confirms and the deterministic scrub of the final JSON is clean. Never transmit the report automatically; if the user declines, log the local path and move on.

## Success report

When migration succeeds, generate a per-workload report with the same structure as the failure report (minus the redaction-to-publish step), listing the patterns detected and the fixes applied for each workload. Write to `~/.databricks-migration-skill/reports/success-<timestamp>.json` and tell the user the file path.

## Multiple workload migration

When several independent workloads are in scope, migrate them in parallel (e.g. one subagent per workload). Keep the per-notebook steps within a single workload sequential, as in Step 1.5.

## Reference Guides

- [Analyze Checklist](references/analyze-checklist.md): Step 2 pattern catalog (A–H, with IDs) and A1 lint
- [Quick Fixes](references/quick-fixes.md): Before/after snippets for the most common fixes
- [Debugging Errors](references/debugging-errors.md): Error → fix table for failed serverless runs
- [Multi-Notebook Workloads](references/multi-notebook-workloads.md): Step 1.5 one-notebook-at-a-time procedure
- [Testing Strategy](references/testing-strategy.md): Branch table, test data, A/B snippet, deliverables
- [Compatibility Checks](references/compatibility-checks.md): Detection details and regexes for 40+ checks
- [Streaming Migration](references/streaming-migration.md): Trigger migration, SDP continuous mode, continuous jobs
- [Networking and Security](references/networking-and-security.md): VPC peering to NCCs, Private Link, firewall setup
- [Code Patterns](references/code-patterns.md): Before/after code for every pattern
- [Configuration Guide](references/configuration-guide.md): Spark configs, Environments, budget policies, job JSON
- [MLflow on UC](references/mlflow-uc-patterns.md): AutoML → sklearn, UC registration, `spark_udf` fix
- [Multi-source enumeration](references/multi-source-enumeration.md): `bundle_config.py` upstream sources
- [Failure Reporting](references/failure-reporting.md): Report schema, redaction, scrub, publish flow
- [Install in Databricks Genie Code](references/install-in-databricks-genie-code.md): Run inside a workspace
- [JAR Migration](references/jar-migration.md): Scala JAR tasks: 2.13.16, Connect, classpath conflicts

## Documentation

- Serverless compute overview: https://docs.databricks.com/compute/serverless/
- **Migration guide**: https://docs.databricks.com/compute/serverless/migration
- Limitations: https://docs.databricks.com/compute/serverless/limitations
- Best practices: https://docs.databricks.com/compute/serverless/best-practices
- Spark Connect vs. classic: https://docs.databricks.com/spark/connect-vs-classic
- More (notebooks, jobs, SDP, UC upgrade, Spark configs): [Configuration Guide](references/configuration-guide.md#documentation)
