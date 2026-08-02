# Spec: audit findings

Measured against clone `50ccd08`. Counts are calibration targets for
`scripts/audit_check.py`. If your measurement disagrees with a count here, the
disagreement is itself a finding — record it, do not silently adopt either
number.

Corpus: 30 stable + 2 experimental skills. Baseline resident set 2,975 tokens
(stable only), 3,199 all-in.

---

## Phase 1 — must-fix (one branch and one PR per finding class)

### SPEC-10a — cross-skill `../` traversal
**Count: 19 skills, 128 occurrences. Target 0.**

Heaviest: `databricks-ml-training` (26), `databricks-unity-catalog` (22),
`databricks-apps-python` (16), `databricks-aibi-dashboards` (11),
`databricks-pipelines` (9), `databricks-mlflow-evaluation` (8),
`databricks-genie-agents` (8), `databricks-spark-structured-streaming` (7).

Fix: replace each cross-skill file path with the bare skill name in prose.
There is no valid cross-skill link form — do not invent one. Then add a
traversal check to `scripts/skillsgen/validators.py` matching the style of the
existing `check_*` functions, so it cannot regress.

### SPEC-10b — bare-basename references
**Count: 11 occurrences in `databricks-mlflow-evaluation`. Target 0.**

All 11 reference files are named in SKILL.md by basename (`GOTCHAS.md`,
`CRITICAL-interfaces.md`, `patterns-scorers.md`, ...) while living under
`references/`. Prefix all 11.

Byte-preserve the rest of that file. Its four numbered workflow tables are the
best routing in the repo; only the paths are wrong.

### PD-5 — reference-to-reference links
**Count: 17 skills. Target 0.**

`databricks-pipelines` (103 — consider its own commit), `unity-catalog` (29),
`spark-structured-streaming` (22), `apps` (21), `aibi-dashboards` (21), plus 12
others.

Fix: strip inter-reference links to plain names; ensure every reference is
linked directly from its SKILL.md with a load condition.

Also flatten `skills/databricks-apps/references/appkit/*.md` to
`references/appkit-*.md` — the only two-level reference directory in the repo.

### PD-1 / PD-2 / PD-3 — ceiling breaches
**Count: 4 skills. Target 0 over either ceiling.**

| Skill | Lines | Tokens | Split |
|---|---|---|---|
| `databricks-serverless-migration` | 839 | 15,683 | "Quick Fixes Reference" → `references/quick-fixes.md`; Step 2 notebook transcripts → `references/analysis-output-examples.md` |
| `databricks-python-sdk` | 625 | 4,470 | split by SDK object family (clusters, jobs, unity catalog, serving) |
| `databricks-aibi-dashboards` | 525 | 8,147 | widget-spec detail into existing `references/` |
| `databricks-pipelines` | 258 | 8,404 | decision tree and Common Traps → `references/` |

`databricks-pipelines` passes the line check and fails on tokens — mean line
128 chars. Both checks bind independently.

Move content verbatim. Do not summarise or rewrite. Leave routing pointers with
load conditions. Total characters across each skill directory must land within
2% of pre-split, which proves content moved rather than vanished.

### PD-4 — dead and missing routing
**Count: 5 defects. Target 0.**

- `databricks-docs` references a skill named
  `databricks-spark-declarative-pipelines` in two places. No such skill exists;
  it is `databricks-pipelines`. Fix both. While in the file, settle terminology
  — it mixes "Delta Live Tables", "DLT", and "Lakeflow" for one product in a
  60-line body.
- `databricks-core` routes to 5 children, but 26 skills declare
  `parent: databricks-core`. Regenerate the Product Skills list from the parent
  graph.
- Three orphan references, linked from nowhere: link with a load condition, or
  delete and say which in the commit message.
  - `databricks-lakebase/references/medallion-from-cdc.md`
  - `databricks-pipelines/references/python-basics.md`
  - `databricks-pipelines/references/sql-basics.md`

### DESC-1 / DESC-3 — descriptions without trigger conditions
**Count: 5 skills. Target 0.**

| Skill | Chars | Problem |
|---|---|---|
| `databricks-agent-bricks` | 122 | bare capability statement, shortest in repo |
| `databricks-vector-search` | 133 | "covers index types, search modes" — contents, not conditions |
| `databricks-execution-compute` | 173 | capability only |
| `databricks-unstructured-pdf-generation` | 253 | capability only |
| `databricks-ai-functions` | 415 | keyword-dense, still no when-clause |

Target 300–500 chars. Hard cap 1,024. Report the resident-set delta against the
2,975-token baseline.

---

## Phase 2 — structural (batch after Phase 1 is green)

### PD-6 — missing reference tables of contents
**Count: ~120 files across 25 skills. Target 0.**

Start with `databricks-metric-views/references/metric-view-advisor.md` — 59,852
chars, the largest single file in the repo, no TOC.

### TOK-5 — uncontained preview and beta markers
**Count: 30 markers across 10 skills. Target 0 bare inline markers.**

Heaviest `databricks-lakeflow-connect` (9), `databricks-pipelines` (6),
`databricks-serverless-migration` (3), `databricks-zerobus-ingest` (3).

Fix: consolidate into a per-skill dated status table or an "old patterns"
section. Do not delete the information.

### Compatibility pin inconsistency
**Count: 4 conflicting values. Target 1, or per-skill values individually
justified.**

`>= v0.292.0` (2, including `databricks-core`), `>= v0.294.0` (5),
`>= v1.0.0` (20), `>= v1.9.0` (1). A repo cannot require CLI 0.292 and 1.9 for
skills that all route through core. Derive from one constant in
`scripts/skillsgen/`.

**Blocked:** requires a verified current Databricks CLI version. Do not guess.
If unverified, plan it and stop.

### GC-1 / GC-8 — no Genie Code surface
**Count: 0 skills. Target 1.**

See `specs/03-genie-code-skill.md`. Authoring task, not a sweep.

### PD-8 / MNT-6 — gotchas and script execution intent
**Count: 29 skills lacking gotchas; 2 skills with scripts lacking
execute-vs-read intent. Lower value, batch last.**

`databricks-ml-training` is the model for a gotchas section.
`databricks-synthetic-data-gen` and `databricks-unstructured-pdf-generation`
bundle scripts without stating whether to run or read them.

---

## File as issue, do not PR

Policy questions for internal maintainers. Upstream cannot merge PRs directly;
these need a decision, not a diff.

- **MNT-1** — `scripts/skills.py validate` checks description presence and
  colon quoting only. Not `name` charset, name-matches-directory, the 1,024
  cap, or the 500-char `compatibility` cap. Propose adding `skills-ref validate`.
- **SPEC-9** — `parent:` is documented in `CONTRIBUTING.md` but absent from the
  Agent Skills spec, which designates `metadata` as the extension point.
  Propose `metadata.parent`; accept a documented rejection.
- **MNT-2** — zero evaluations across 32 skills against a published floor of
  three per skill.
- **MNT-8** — `metadata.version` is inert: 21 skills at `0.1.0`, nothing bumps
  on content change, releases run off `version.meta.json` (`0.2.10`). One value
  is unquoted.
- **DBX-3** — `docs.databricks.com/aws/en/agent-skills/` lists 8 skills; the
  repo ships 30. Same table lists AI Dev Kit as live while
  `experimental/README.md` calls it deprecated. Docs-side.
- **MNT-7a** — `experimental/README.md` self-contradicts on re-sync cadence.
- **MNT-7b** — `.gen.json` pins `source_commit: 70f06e3`, not an object in this
  repo's history.

## Withdrawn

- **SPEC-11** — `agents/openai.yaml` and `assets/` sit outside the spec's
  conventional directory set, but `CONTRIBUTING.md` requires both for every
  skill as Codex marketplace metadata. Deliberate. Not a defect.
