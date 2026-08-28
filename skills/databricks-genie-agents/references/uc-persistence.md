# Genie Optimization — UC Table Persistence DDL

Reference for creating and using Unity Catalog Delta tables to persist multi-pass Genie Agent optimization history. Load this file when the user has approved a catalog/schema location and you need to initialize or query the history tables.

> This is optional infrastructure. Use native benchmark output without these tables when persistence is not requested.

## Default: Four Tables

```sql
-- Run ledger: one row per optimization pass / candidate edit
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_runs (
  run_id              STRING NOT NULL,
  session_id          STRING,
  space_id            STRING NOT NULL,
  space_name          STRING,
  benchmark_execution_target  STRING,   -- Chat | Agent | mixed
  benchmark_id        STRING,
  benchmark_version_or_hash   STRING,
  iteration           INT,
  parent_run_id       STRING,
  baseline_config_version_id  STRING,
  candidate_config_version_id STRING,
  target_cluster      STRING,
  repair_lever        STRING,
  status              STRING,           -- in_progress | kept | revised | rolled_back
  started_at          TIMESTAMP,
  ended_at            TIMESTAMP,
  baseline_score      DOUBLE,
  candidate_score     DOUBLE,
  score_delta         DOUBLE,
  fixed_count         INT,
  regressed_count     INT,
  unchanged_bad_count INT,
  unchanged_good_count INT,
  excluded_count      INT,
  decision            STRING,           -- KEEP | REVISE | ROLL_BACK
  notes               STRING
) USING DELTA;

-- Config snapshots: one row per before/after Agent config capture
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_config_versions (
  config_version_id       STRING NOT NULL,
  run_id                  STRING NOT NULL,
  space_id                STRING NOT NULL,
  version_label           STRING,       -- before | after
  parent_config_version_id STRING,
  captured_at             TIMESTAMP,
  captured_by             STRING,
  config_hash             STRING,
  config_json             STRING,       -- full serialized_space JSON
  changed_surfaces        STRING,       -- comma-separated surface names
  change_summary          STRING
) USING DELTA;

-- Eval results: one row per benchmark question per eval run
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_eval_results (
  eval_result_id          STRING NOT NULL,
  eval_run_id             STRING NOT NULL,
  run_id                  STRING NOT NULL,
  space_id                STRING NOT NULL,
  benchmark_id            STRING,
  benchmark_version_or_hash STRING,
  eval_type               STRING,       -- Chat | Agent
  evaluated_at            TIMESTAMP,
  question_id             STRING,
  question_text           STRING,
  benchmark_field_strategy STRING,      -- single_sql_answer | deterministic_with_response_quality | multi_step_agent_analysis
  assessment              STRING,       -- GOOD | BAD | NEEDS_REVIEW
  valid_tuning_failure    BOOLEAN,
  exclusion_reason        STRING,
  primary_failure         STRING,
  secondary_signal        STRING,
  failure_cluster         STRING,
  expected_sql_hash       STRING,
  generated_sql_hash      STRING,
  generated_sql           STRING,
  evaluation_note_hash    STRING,
  expected_result_digest  STRING,
  actual_result_digest    STRING,
  judge_notes             STRING,
  latency_ms              BIGINT,
  error_message           STRING
) USING DELTA;

-- Repair analysis: one row per failure cluster / repair hypothesis per pass
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_repair_analysis (
  analysis_id             STRING NOT NULL,
  run_id                  STRING NOT NULL,
  space_id                STRING NOT NULL,
  created_at              TIMESTAMP,
  cluster_id              STRING,
  affected_question_ids   STRING,       -- JSON array
  root_cause              STRING,
  evidence_summary        STRING,
  selected_lever          STRING,
  rejected_levers         STRING,
  config_surface          STRING,
  planned_patch_summary   STRING,
  expected_fix_count      INT,
  regression_risk         STRING,
  benchmark_leakage_check STRING,
  acceptance_decision     STRING,
  reflection              STRING,
  next_hypothesis         STRING
) USING DELTA;
```

## Minimum Viable Alternative: Three Tables

Merge repair analysis into the run row as a JSON column:

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_runs (
  -- all columns above, plus:
  repair_analysis_json    STRING        -- JSON of cluster, lever, evidence, reflection
) USING DELTA;

CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_config_versions ( ... );
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_eval_results ( ... );
```

## Single Append-Only Event Table

For maximum setup simplicity at the cost of typed queries:

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_events (
  event_id            STRING NOT NULL,
  event_ts            TIMESTAMP NOT NULL,
  event_type          STRING NOT NULL,  -- run_started | config_snapshot | eval_question_result | repair_analysis | candidate_decision | iteration_reflection
  session_id          STRING,
  run_id              STRING,
  space_id            STRING,
  config_version_id   STRING,
  eval_run_id         STRING,
  question_id         STRING,
  payload_json        STRING            -- full event payload as JSON
) USING DELTA;
```

## Per-Pass Write Order

When persistence is enabled for a candidate pass:

1. Write a `genie_opt_runs` row (status = `in_progress`).
2. Capture the before-config snapshot in `genie_opt_config_versions`.
3. Write the repair analysis row before editing.
4. Apply the focused Agent/config edit.
5. Capture the after-config snapshot in `genie_opt_config_versions`.
6. Write question-level eval results to `genie_opt_eval_results`.
7. Update the `genie_opt_runs` row with the acceptance decision, score delta, and iteration reflection.
