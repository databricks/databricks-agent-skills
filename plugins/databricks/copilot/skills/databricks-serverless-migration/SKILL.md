---
name: databricks-serverless-migration
description: "Migrate Databricks workloads from classic compute to serverless compute. Use when migrating notebooks, jobs, pipelines, or Scala JARs (`spark_jar_task`) from classic clusters to serverless, checking if existing code is serverless-compatible, or writing new serverless-compatible code. Provides concrete fixes for the serverless Spark Connect architecture and guides the full migration. Not for classic DBR version upgrades or cluster configuration changes within classic compute."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.0"
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

This skill is published as an Agent Skill (agentskills.io) and runs in any compatible client:

- **Claude Code, Cursor, or any agentskills.io client on your laptop** — the default. Install via `databricks aitools install` or follow the per-client docs.
- **Inside a Databricks workspace via Genie Code Agent mode** — drop the skill into `/Workspace/Users/<you>/.assistant/skills/databricks-serverless-migration/` (per-user) or `/Workspace/.assistant/skills/databricks-serverless-migration/` (workspace-wide, admin only). See [Install in Databricks Genie Code](references/install-in-databricks-genie-code.md) for the three install methods and the **important serverless-compute caveat** (the Databricks CLI isn't pre-installed on serverless, so some deploy steps need adjustment).

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

If the workload spans more than one user notebook (exclude `_resources/` setup notebooks from the count), process them **one at a time** rather than all at once. The agent's context window is finite, and trying to hold the full source of an 8-notebook job in active context while doing analysis, fixes, and migration triggers autocompact thrashing (Claude Code) or equivalent context-overflow failures in other clients.

**Procedure**:

1. **Enumerate first.** List every user notebook with its path. Do not read the bodies in full yet beyond a few lines for orientation.
   - **Check for `bundle_config.py` (H4).** If the source tree contains a `bundle_config.py`, parse it and follow any upstream-source declarations (git URLs, S3 paths, `init_scripts`, `git_source`, or custom upstream-repo declarations). Clone or fetch each referenced repo into a sibling location and include its notebooks in the enumeration. List "external sources" as a first-class artifact category in the migration plan. Without this step, multi-source demos (e.g., `dbt-on-databricks` references the upstream `dbt-databricks-c360` repo) get mis-enumerated and the real task notebooks are missed.
2. **For each notebook, in order**:
   a. Read its full source.
   b. Run the Step 2 Analyze checklist scoped to this notebook only.
   c. Record a structured summary in your response or to a scratch file, then drop the raw source from active working memory. The summary must include:
      - `notebook_path` (relative)
      - `detected_patterns[]` (pattern IDs from this skill's catalog)
      - `blockers[]` (Category-3 patterns this notebook hits, if any)
      - `migration_steps[]` (concrete fixes ordered)
      - `unmigratable` (bool — true if any blocker has no workaround)
   d. If you have a writable scratch directory (`~/.databricks-migration-skill/scratch/<run-id>/findings/`), persist the summary as `<notebook-basename>.json`. This frees the source from context safely. If not, keep the summary compact in conversation history.
3. **Synthesize.** After all notebooks have a summary, produce the unified migration plan from the summaries alone. Apply fixes notebook-by-notebook, never re-reading the original source unless required to resolve an ambiguity in a summary.
4. **Failure Reporting.** Trigger the Failure Reporting Protocol exactly once per workload, not once per notebook. The `detected_patterns` array in the report aggregates across all notebooks; `notebook_characteristics` uses summed line counts and the union of language/streaming/ML flags.

**Threshold guidance**: apply this procedure when the user notebook count is ≥ 3, or when individual notebooks exceed ~5KB of source. For 1–2 small notebooks the single-pass workflow in Steps 2–4 is fine.

**Anti-pattern**: do NOT attempt a "merge all notebooks into one big file" or "read all notebooks, then act in one mega-turn" strategy. Both defeat the purpose by reintroducing the original context-pressure problem.

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

#### Post-rewrite lint and the full finding catalogue

**HIGH IMPACT.** Read
[Analysis Output Examples](references/analysis-output-examples.md) after
rewriting any notebook and before declaring it ready. It carries the
cell-magic boundary lint (A1), the finding catalogue for categories A–G, and
the deployment-blocker table (H1–H4).

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

**Important**: ML runtime libraries (mlflow, scikit-learn, hyperopt, xgboost, tensorflow, torch, etc.) are NOT pre-installed on serverless compute. They MUST be listed explicitly in the environment spec `dependencies`. ML runtime is NOT available on serverless — always use Serverless Environments with explicit package dependencies instead.

### Step 3: Test — Two-Branch Strategy

Read [Testing Strategy](references/testing-strategy.md) before running the
first test: it carries the test-versus-production branch table, test data
setup, the decision tree for whether a change belongs in production, and the
A/B comparison procedure.

### Step 4: Validate — Confirm and Monitor

Once the A/B comparison passes:
1. Merge the production branch PR
2. Switch the production job to serverless compute
3. Monitor cost via system tables (`system.billing.usage`) and budget policies
4. Remove any temporary bridge configurations
5. Set up budget alerts for cost visibility

### Migration Deliverables

At the end of a successful migration run, surface these artifacts so the user can verify the work and inspect the results:

| Deliverable | What it is | Why it matters |
|-------------|------------|----------------|
| Test branch name/URL | The `serverless-test-{job_name}-{timestamp}` branch with all compatibility fixes and test workarounds | Lets the user see what changed during experimentation, including test-only adjustments |
| Production branch name/URL | The `serverless-prod-{job_name}` branch containing only the validated compatibility fixes | This is what ships — the user reviews and merges the PR from here |
| Test job ID and run URL | The serverless test job that validated the migration | Proves the notebook runs successfully on serverless against sampled data |
| Classic vs serverless comparison | A/B result summary (row counts, schema check, row-level diff) | Confidence that serverless output matches classic output |
| Serverless environment spec | The `environments` JSON block (client version + pinned dependencies) | Ready to paste into the production job config |
| Change summary | List of what went to production vs test-only (with reasons) | Audit trail for the PR reviewer |

If any deliverable is missing, the migration is incomplete — do not mark it as done.

### Stopping Conditions

Do not attempt workarounds for these — surface them to the user and stop:
- Permission failures on source tables, the test catalog, or the workspace
- Category 3 blockers (R code, custom Spark data source JARs, features that require classic compute)
- SQL warehouse or test catalog not available
- Repeated failures (typically 5+) with no new information in the error trace — generate a failure report instead (see Failure Reporting Protocol)

## Quick Fixes Reference

Read [Quick Fixes](references/quick-fixes.md) when a scan has flagged a
pattern and you need the concrete rewrite: DBFS paths to UC Volumes, RDD
operations to DataFrames, streaming triggers, cache removal, runtime
serverless detection, classic-to-serverless job config transforms, job
definition migration, catalog parameterization for testing, and debugging
failed serverless runs.

## Performance Mode Selection

| Criteria | Performance-Optimized | Standard |
|----------|-----------------------|----------|
| Startup time | <50 seconds | 4-6 minutes |
| Cost | Higher | Significantly lower |
| Available for | Notebooks, Jobs, SDP | Jobs and SDP only |
| Best for | Interactive work, dev, time-sensitive | Batch ETL, scheduled pipelines |
| Default | Yes (UI and API) | Must be explicitly selected |

**Standard mode is NOT available for notebooks.** Notebooks always use Performance-Optimized.

## Serverless Defaults to Know

| Setting | Value |
|---------|-------|
| REPL VM memory | 8GB default (high-memory option available) |
| Max executors | 32 (Premium), 64 (Enterprise) — raise via support |
| Supported Spark configs | 6 only (see Category D above) |
| Debugging | Query Profile (no Spark UI) |
| ANSI SQL | Enabled by default (configurable) |

## Failure Reporting Protocol

When migration fails or hits an unmigratable pattern, generate a structured failure report and offer the user a one-step path to file it as a GitHub issue. This feedback loop is how the skill learns — without it, gaps go undiscovered.

See [Failure Reporting](references/failure-reporting.md) for the full redaction checklist, URL-encoding recipe, and example pre-filled link.

The decision tree for when to offer, how to generate the report, what it
must not contain, the anonymization safety pass, the deterministic
post-serialization scrub, and the output template are all in that
reference — read it before generating any report.

## Success report

When migration succeeds, generate a per-workload report with the same structure as the failure report (minus the redaction-to-publish step), listing the patterns detected and the fixes applied for each workload. Write to `~/.databricks-migration-skill/reports/success-<timestamp>.json` and tell the user the file path.

## Multiple workload migration

When several independent workloads are in scope, migrate them in parallel (e.g. one subagent per workload). Keep the per-notebook steps within a single workload sequential, as in Step 1.5.

## Reference Guides

For detailed workarounds and code examples beyond the quick fixes above:

- [Compatibility Checks](references/compatibility-checks.md) — Full pattern detection table with all 40+ checks
- [Streaming Migration](references/streaming-migration.md) — Trigger migration, SDP continuous mode, continuous jobs
- [Networking and Security](references/networking-and-security.md) — VPC peering to NCCs, Private Link, firewall setup
- [Code Patterns](references/code-patterns.md) — Complete before/after code examples for every migration pattern
- [Configuration Guide](references/configuration-guide.md) — Supported Spark configs, Environments setup, budget policies
- [MLflow on UC](references/mlflow-uc-patterns.md) — AutoML rewrite to sklearn, UC-aware registration, `latest_versions` replacement, `spark_udf` closure-bug fix, prediction-column dtype alignment
- [Multi-source enumeration](references/multi-source-enumeration.md) — Parsing `bundle_config.py` and fetching upstream git sources before per-notebook analysis
- [Failure Reporting](references/failure-reporting.md) — Redaction checklist + pre-filled GitHub issue URL recipe (for when migration cannot complete)
- [Install in Databricks Genie Code](references/install-in-databricks-genie-code.md) — Run this skill inside a Databricks workspace
- [JAR Migration](references/jar-migration.md) — Migrating a compiled Scala JAR (spark_jar_task): Scala 2.13.16, Databricks Connect, dependency conflicts vs the serverless kernel classpath, sbt fixes, build/test/deploy

## Documentation

- Serverless compute overview: https://docs.databricks.com/en/compute/serverless/
- **Migration guide**: https://docs.databricks.com/en/compute/serverless/migration
- Limitations: https://docs.databricks.com/en/compute/serverless/limitations
- Best practices: https://docs.databricks.com/en/compute/serverless/best-practices
- Serverless notebooks: https://docs.databricks.com/en/compute/serverless/notebooks
- Serverless jobs: https://docs.databricks.com/en/jobs/run-serverless-jobs
- Serverless SDP: https://docs.databricks.com/en/ldp/serverless
- Spark Connect vs. classic: https://docs.databricks.com/en/spark/connect-vs-classic
- Unity Catalog upgrade: https://docs.databricks.com/en/data-governance/unity-catalog/upgrade/
- Supported Spark configs: https://docs.databricks.com/en/spark/conf#serverless
