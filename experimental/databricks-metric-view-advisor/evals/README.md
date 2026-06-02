# Evals — databricks-metric-view-advisor

Two layers of evaluation for this skill. A skill is agent *instructions*, so
"eval" means two distinct things: does the documentation stay correct and
self-consistent (static), and does an agent following it produce correct,
deployable metric views (behavioral).

## Layer 1 — Static consistency (`check_examples.py`)

Runs with **no workspace**. Lints the skill's own files to catch documentation
drift — exactly the class of bug that a targeted edit can introduce (a stale
duplicate in a sibling reference file that contradicts the new guidance).

```bash
python3 evals/check_examples.py            # static checks only
python3 evals/check_examples.py --live      # also probe `databricks ... --help`
python3 evals/check_examples.py --live --profile <PROFILE>
```

Checks: every concrete metric-view YAML example parses and has the required
fields; no `format:` blocks; multi-word `MEASURE()` refs are backtick-quoted; no
date-subtraction (DATEDIFF rule); every documented Python snippet compiles;
fixture files parse; only real `aitools`
subcommands are referenced (and, with `--live`, that they exist in the installed
CLI); regression guards for the two review fixes (no raw `/api/2.0/sql/statements`,
re-auth without `--host`); and all relative links resolve.

Wire it into CI to block doc-drift regressions on every PR.

## Layer 2 — Behavioral scenarios (`SCENARIOS.md`)

Requires a **workspace** with seed data. Defines one scenario per input source
(plus a combined one), each with: setup, the scripted user turns to feed the
skill, the expected deliverables, and a pass/fail rubric. The end-state assertion
is objective and automatable: **the generated metric view deploys and a
`MEASURE() + GROUP BY` query returns rows.**

See `SCENARIOS.md` for the matrix, the seed-data setup (`samples.tpch` is a good
zero-setup source), and the scoring rubric.

## What "passing" means

- **Layer 1:** exit code 0 (all cases pass). Cheap, deterministic, run on every change.
- **Layer 2:** every scenario's metric view deploys cleanly and its sample
  queries return rows, and the rubric score meets the bar. Run before releases or
  after changes to the analysis/generation logic.
