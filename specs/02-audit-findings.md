# Spec: audit findings

Measured against clone `50ccd08`, which is `upstream/main` itself. The corpus is
unremediated: `skills/` (tree `4675ac0`) and `experimental/` (tree `32b7073`) are
byte-identical to `upstream/main`, so `python3 scripts/audit_check.py` run in a
working tree on this branch *is* the upstream baseline — no worktree or detached
checkout needed.

**Every `Count:` below is the checker's number in the checker's unit**, tagged
with the `audit_check.py` row ID that reports it. The unit is named explicitly —
occurrences, links, files, mentions, skills, or descriptions — because the
original audit and the checker frequently measure the same defect at different
granularity, and a target stated in the wrong unit cannot be gated. Where the
audit's stated figure differs, it is preserved in the Reconciliation section
below rather than discarded; the disagreement is itself a finding.

Baseline totals: **568 must-fix** across 31 skills. Resident set 2,975 tokens
(stable only), 3,199 all-in.

Corpus: 30 stable + 2 experimental skills.

Backpressure per finding: `python3 scripts/audit_check.py --only <row-id>`. The
row IDs used as tags below are exactly the IDs that flag accepts.

---

## Phase 1 — must-fix (one branch and one PR per finding class)

### SPEC-10a — `../` traversal

The audit's single count conflates four classes with different fixes. The
checker reports each separately, and the units differ per class.

**Count (`SPEC-10a-cross`): 90 links across 20 skills. Target 0.**
**Count (`SPEC-10a-intra`): 21 links across 9 skills. Target 0.**
**Count (`SPEC-10a-prose`): 0. Target 0 — already clean.**
**Exempt (`SPEC-10a-fence`, advisory): 81 occurrences across 5 skills.**
**Exempt (`SPEC-10a-self-parent`, advisory): 3 occurrences in 1 skill.**

The unit is **links**, not occurrences: a `../../` target matches the traversal
regex twice, so the same 90 cross-skill links are 111 `../` occurrences. Audit
said 19 skills / 128 occurrences — see Reconciliation.

Heaviest cross-skill (`SPEC-10a-cross`, links): `databricks-ml-training` (14),
`databricks-unity-catalog` (11), `databricks-apps-python` (8),
`databricks-pipelines` (7), `databricks-spark-structured-streaming` (7),
`databricks-aibi-dashboards` (6), `databricks-genie-agents` (4),
`databricks-mlflow-evaluation` (4).

Heaviest intra-skill (`SPEC-10a-intra`, links): `databricks-pipelines` (5),
`databricks-ml-training` (4), `databricks-agent-bricks` (3),
`databricks-ai-functions` (3), `databricks-apps` (2), then 1 each in
`databricks-aibi-dashboards`, `databricks-lakeflow-connect`,
`databricks-metric-views`, `databricks-serverless-migration`.

Fix (`SPEC-10a-cross`): replace each cross-skill file path with the bare skill
name in prose. There is no valid cross-skill link form — do not invent one.
Fix (`SPEC-10a-intra`): rewrite the path relative to the skill root. Then add a
traversal check to `scripts/skillsgen/validators.py` matching the style of the
existing `check_*` functions, so it cannot regress.

Clearing `SPEC-10a-cross` also clears all 6 `NEW-A` links — they are the same
links, counted once as traversals and once as dangling targets.

### SPEC-10b — bare-basename references
**Count (`SPEC-10b`): 64 mentions across 2 skills. Target 0.**

Units: 64 counts *mentions*; 11 counts reference *files*. Both are correct
measurements of the same defect at different granularity. `databricks-mlflow-evaluation`
carries 61 mentions, `databricks-app-design` 3 — a second skill the original
audit did not name.

None are markdown links, so a `](...)`-only regex finds zero. Two exclusions are
load-bearing: a basename in a link *label* routes correctly and counting labels
inflates the class to 167; and a basename that resolves at the skill root is a
different finding (NEW-C). Full derivation in the reconciliation section below.

Byte-preserve the rest of `databricks-mlflow-evaluation/SKILL.md`. Its four
numbered workflow tables are the best routing in the repo; only the paths are
wrong.


### NEW-A — dangling relative `.md` links
**Count (`NEW-A`): 6 links in 1 skill. Target 0.**

Not in the original audit. All 6 sit in
`skills/databricks-spark-structured-streaming/references/lakebase-sink-python.md`
at `:13` (×2), `:20`, `:117`, `:277`, `:312`, and all target
`../databricks-lakebase/references/{connectivity,computes-and-scaling,lakehouse-sync}.md`
— paths that do not exist under any spelling.

The unit is **links**, the same unit as `SPEC-10a-cross`, and these are the same
6 links: they are counted once for traversing out of the skill and once for not
resolving. Fixing the cross-skill sweep zeroes both rows; no separate commit.

### PD-5 — reference-to-reference links
**Count (`PD-5`): 228 links across 15 skills. Target 0.**

The unit is **links to strip**, not skills carrying the defect — the audit
counted skills (17). Heaviest: `databricks-pipelines` (91 — consider its own
commit), `databricks-unity-catalog` (29), `databricks-aibi-dashboards` (19),
`databricks-apps` (19), `databricks-spark-structured-streaming` (15),
`databricks-metric-views` (13), `databricks-lakebase` (9),
`databricks-ml-training` (8), `databricks-execution-compute` (6),
`databricks-iceberg` (6), `databricks-apps-python` (5), then 2 each in
`databricks-lakeflow-connect`, `databricks-serverless-migration`,
`databricks-zerobus-ingest`, `spark-python-data-source`.

Fix: strip inter-reference links to plain names; ensure every reference is
linked directly from its SKILL.md with a load condition.

Clearing `PD-5` also clears all 3 `PD-4c` orphans — the second clause of that
fix *is* the PD-4c fix. See PD-4c.

### PD-5b — nested `references/` subdirectory
**Count (`PD-5b`): 12 files in 1 skill. Target 0.**

References are one level deep. Every file under
`skills/databricks-apps/references/appkit/` breaches it — the only two-level
reference directory in the repo. Flatten to `references/appkit-*.md`.

The audit described this inside PD-5's prose but never gave it a count. It is a
separate row with a separate gate (`--only PD-5b`) because the fix is a rename,
not a link edit, and the unit is **files moved**, not links stripped.

### PD-1 / PD-2 / PD-3 — ceiling breaches
**Count (`PD-1`): 3 skills over 500 lines. Target 0.**
**Count (`PD-2`): 3 skills over 5,000 tokens. Target 0.**
**Count (`PD-3`, rollup): 4 skills over either ceiling. Not a gate — the union
of PD-1 and PD-2, reported so the audit's stated 4 stays traceable.**

The unit is **skills** in all three rows. The audit's single "4 skills" is the
`PD-3` rollup; because the two ceilings bind independently, two of the four
breach only one of them, so neither must-fix row is 4.

| Skill | Lines | Tokens | Breaches | Split |
|---|---|---|---|---|
| `databricks-serverless-migration` | 839 | 15,683 | PD-1 + PD-2 | "Quick Fixes Reference" → `references/quick-fixes.md`; Step 2 notebook transcripts → `references/analysis-output-examples.md` |
| `databricks-python-sdk` | 625 | 4,470 | PD-1 only | split by SDK object family (clusters, jobs, unity catalog, serving) |
| `databricks-aibi-dashboards` | 525 | 8,147 | PD-1 + PD-2 | widget-spec detail into existing `references/` |
| `databricks-pipelines` | 258 | 8,404 | PD-2 only | decision tree and Common Traps → `references/` |

`databricks-pipelines` passes the line check and fails on tokens — mean line
128 chars. Both checks bind independently.

Move content verbatim. Do not summarise or rewrite. Leave routing pointers with
load conditions. Total characters across each skill directory must land within
2% of pre-split, which proves content moved rather than vanished.

### PD-4 — dead and missing routing

The audit's "5 defects" is one headline over three checker rows with three
units, three fixes, and — for `PD-4b` — a different severity.

#### PD-4a — pointer to a nonexistent skill
**Count (`PD-4a`): 3 occurrences across 2 skills. Target 0.**

`databricks-spark-declarative-pipelines` does not exist; it is
`databricks-pipelines`. Occurrences at `databricks-docs/SKILL.md:23` and `:52`
and `experimental/spark-python-data-source/SKILL.md:145` — three, not the two
the audit named, and the third is in a skill the audit did not name. While in
`databricks-docs`, settle terminology — it mixes "Delta Live Tables", "DLT", and
"Lakeflow" for one product in a 60-line body.

#### PD-4b — core children missing from core routing
**Count (`PD-4b`): 19 skills unrouted. Blocked, not must-fix.**

The unit is **skills absent from `databricks-core/SKILL.md`**, not the audit's
count of skills declaring the parent. 25 skills declare
`parent: databricks-core` (not 26); `databricks-core` mentions 6 of them; 19 are
unreachable from core.

Blocked because regenerating the Product Skills list from the parent graph is a
routing-policy decision — whether every child belongs in core's body, or only a
curated set, is a maintainer call. The checker reports it and does not gate on
it.

#### PD-4c — orphan reference files
**Count (`PD-4c`): 3 files across 2 skills. Target 0.**

Linked from nowhere: link with a load condition, or delete and say which in the
commit message.

- `databricks-lakebase/references/medallion-from-cdc.md`
- `databricks-pipelines/references/python-basics.md`
- `databricks-pipelines/references/sql-basics.md`

**Not an independent class — a consequence of `PD-5`.** All three cleared inside
the PD-5 sweeps, with no PD-4c pass of their own. Each was reachable only
through a second hop, and a reference reachable only that way is an orphan
whether or not an orphan checker notices — this row happens to, because it is
rooted at SKILL.md. PD-5's fix already ends "ensure every reference is linked
directly from its SKILL.md with a load condition" — that clause *is* this fix,
which is why the sweep that strips the hop must re-route the file in the same
commit. The row stays, because it is what catches a *new* orphan; the branch
does not — **`ralph/pd-4c-orphans` is retired.**

### DESC-1 / DESC-3 — descriptions without trigger conditions
**Count (`DESC-1`): 6 descriptions across 6 skills. Target 0.**

The unit is **descriptions** — one per skill, so the skill count matches. The
audit named 5; the checker finds 6.

| Skill | Chars | Problem |
|---|---|---|
| `databricks-agent-bricks` | 122 | bare capability statement, shortest in repo |
| `databricks-vector-search` | 133 | "covers index types, search modes" — contents, not conditions |
| `databricks-execution-compute` | 173 | capability only |
| `databricks-unstructured-pdf-generation` | 253 | capability only |
| `databricks-genie-agents` | 350 | capability only — the sixth, unnamed by the audit |
| `databricks-ai-functions` | 415 | keyword-dense, still no when-clause |

Target 300–500 chars. Hard cap 1,024. Report the resident-set delta against the
2,975-token baseline.

`databricks-genie-agents` is the reason length alone is not the gate: at 350
chars it already sits inside the 300–500 target band and still states no
condition for firing.

### NEW-C — reference files at the skill root
**Count (`NEW-C`): 4 files across 2 skills. Target 0.**

Not in the original audit, but load-bearing for two findings that already cite
it. Reference content sitting beside `SKILL.md` instead of under `references/`
resolves fine on disk, so nothing looks broken — while every `references/`-scoped
check (TOC, orphan, one-level-deep) skips it silently.

- `skills/databricks-core/databricks-cli-auth.md`
- `skills/databricks-core/databricks-cli-install.md`
- `skills/databricks-core/manual-data-exploration.md`
- `experimental/databricks-ai-runtime/docker-images.md`

All four are over 100 lines and none carries a TOC, so they are also 4 of the
125 `PD-6` files. The `PD-6` and `SPEC-10b` reconciliations below both defer to
"the root-file finding" — this is it.

---

## Phase 2 — structural (batch after Phase 1 is green)

### PD-6 — missing reference tables of contents
**Count (`PD-6`): 125 files across 26 skills. Target 0.**

The unit is **files lacking a TOC**, and it includes the 4 `NEW-C` root-level
files — excluding them is the exact blind spot the root-file finding describes.
Audit said ~120 across 25 skills.

Heaviest: `databricks-apps` (14), `databricks-pipelines` (13),
`databricks-spark-structured-streaming` (11), `databricks-serverless-migration`
(8), `spark-python-data-source` (8), `databricks-lakebase` (7),
`databricks-unity-catalog` (7).

Start with `databricks-metric-views/references/metric-view-advisor.md` — 59,852
chars, the largest single file in the repo, no TOC.

### TOK-5 — uncontained preview and beta markers
**Count (`TOK-5`): 21 markers across 10 skills, strict basis. Blocked.**

The unit is **markers**. Blocked, not must-fix: the audit's 30 reproduces under
no basis, so the definition is a maintainer decision and no sweep should run
against an unreproducible number. See Reconciliation.

Heaviest on the strict basis the checker reports: `databricks-pipelines` (8),
`databricks-zerobus-ingest` (3), `databricks-iceberg` (2),
`databricks-ml-training` (2), then 1 each in `databricks-apps`,
`databricks-apps-python`, `databricks-lakebase`, `databricks-lakeflow-connect`,
`databricks-mlflow-evaluation`, `databricks-spark-structured-streaming`.

Note this list barely overlaps the audit's: `databricks-lakeflow-connect` is 1
strict, not 9, and `databricks-serverless-migration` is 0 under every basis —
the phantom the reconciliation isolates.

Fix, once unblocked: consolidate into a per-skill dated status table or an "old
patterns" section. Do not delete the information.

### COMPAT-1 — compatibility pin inconsistency
**Count (`COMPAT-1`): 7 = 5 excess pin shapes + 2 body-vs-frontmatter
conflicts. Blocked. Target 1 surviving shape and 0 conflicts.**

The unit is **excess shapes**, not conflicting values: the checker charges one
shape as the target and counts every additional one, so the row reaches zero
when a single shape remains. Six distinct shapes exist across the 32 skills —

| Shape | Skills |
|---|---|
| *(no `compatibility` field)* | 3 |
| `>= v0.292.0` | 2, including `databricks-core` |
| `>= v0.294.0` | 5 |
| `>= v1.0.0` | 20 |
| `>= v1.9.0` (`databricks genie ask`) | 1 |
| `databricks-air` CLI | 1 |

— of which 6 − 1 = 5 are excess. The audit's 4 counted only the four numeric
CLI pins. A repo cannot require CLI 0.292 and 1.9 for skills that all route
through core. Derive from one constant in `scripts/skillsgen/`.

The 2 conflicts are a skill's own body contradicting its frontmatter pin:
`databricks-jobs/SKILL.md:44` (body v0.288.0) and
`databricks-python-sdk/SKILL.md:24` (body 0.278.0), both against `>= v1.0.0`.
These are mechanically fixable without knowing the target floor — the body and
the frontmatter of one file disagree regardless of which value is right.

**Blocked:** requires a verified current Databricks CLI version. Do not guess.
If unverified, plan it and stop.

### GC-1 / GC-8 — no Genie Code surface
**Count: 0 skills. Target 1. No `audit_check.py` row** — an authoring task has
no defect count to measure until the skill exists, at which point the ordinary
rows gate it.

See `specs/03-genie-code-skill.md`. Authoring task, not a sweep.

### PD-8 / MNT-6 — gotchas and script execution intent
**Count (`PD-8`, advisory): 30 SKILL.md with no gotchas section.**
**Count (`MNT-6`, advisory): 1 skill bundling `scripts/` with no stated intent.**

Units are **skills** in both. Audit said 29 and 2. Lower value, batch last.

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
- **NEW-B** — **1 link, advisory.**
  `skills/databricks-apps/references/appkit/proto-first.md:306` links
  `references/plugin-contracts.md`, which exists nowhere in the repo under any
  path. Which file it meant is a maintainer decision, so it is held out of
  `NEW-A` and reported on its own — guessing a target ships a wrong pointer.

## Exempt (advisory, counted for context only)

Reported by the checker, never a defect. Listed so a reader who sees the number
in the rollup can find its rationale.

- **`SPEC-10a-fence` — 81 occurrences across 5 skills.** `../` inside a code
  fence is a working example (DAB `notebook_path:` values, TypeScript imports,
  one deliberate failing `%run`). Rewriting them would break the examples.
- **`SPEC-10a-self-parent` — 3 occurrences in 1 skill.** `../SKILL.md` from a
  `references/` file names the skill's own parent, at
  `databricks-metric-views/references/metric-view-advisor.md:18`, `:28`, `:808`.
  The path never leaves the skill directory, so no subset install can break it —
  which is the sole rationale for the SPEC-10a class.

## Withdrawn

- **SPEC-11** — `agents/openai.yaml` and `assets/` sit outside the spec's
  conventional directory set, but `CONTRIBUTING.md` requires both for every
  skill as Codex marketplace metadata. Deliberate. Not a defect.

## Reconciliation (measured by scripts/audit_check.py)

Counts re-measured while building `scripts/audit_check.py`. Where a count above
and the corpus disagree, the checker implements the corpus.

**MNT-6 — spec 2 skills, corpus 1; checker 1.** The PDF skill states run intent
plainly: `skills/databricks-unstructured-pdf-generation/SKILL.md:17` ("Convert
HTML → PDF using `<SKILL_ROOT>/scripts/pdf_generator.py`"), literal invocation
at `:43`, file manifest at `:124`, recreate-if-absent fallback at `:126`. Only
`databricks-synthetic-data-gen` lacks it, and worse than stated: its
`scripts/generate_synthetic_data.py` (300 lines) is referenced nowhere in the
skill — SKILL.md, `references/`, `agents/`, `assets/` all return zero. That
residual defect is orphan-script, not missing-intent.

**TOK-5 — spec 30 markers / 10 skills; no basis reproduces it; checker 21,
blocked.** Strict parenthesised `(Public Preview|Private Preview|Beta)` over
all `.md` = 21 / 10 skills; broad case-insensitive = 87 / 15; broad on SKILL.md
only = 27 / 9; strict on SKILL.md only = 7 / 3. The named figures
(`lakeflow-connect` 9, `pipelines` 6, `zerobus-ingest` 3) match the broad
SKILL.md basis, but the fourth named skill `databricks-serverless-migration`
(3) has zero preview/beta markers of any kind, strict or broad, across all 11
of its `.md` files: 30 = 27 + a phantom 3. The checker reports the strict basis
and stays blocked until a maintainer picks the definition; no sweep should run
against an unreproducible number.

**PD-6 — spec ~120 files / 25 skills, corpus 125 / 26; checker 125.** 121 of
the 125 sit under `references/`; the other 4 are root-level reference files
(`databricks-cli-auth.md`, `databricks-cli-install.md`,
`manual-data-exploration.md` in `skills/databricks-core/`, plus
`experimental/databricks-ai-runtime/docker-images.md`) — all over 100 lines,
none with a TOC. Totals: 168 under `references/` + 4 at skill roots = 172
files; 133 + 4 = 137 over 100 lines; 121 + 4 = 125 lacking a TOC. Root-level
files are included because excluding them is the exact blind spot the root-file
finding describes.

**SPEC-10a — spec 128 occurrences / 19 skills conflates four classes with
different fixes; the checker counts each separately.** A naive `\.\./` finds
240; 14 are `...` truncation markers (`/Volumes/.../file.csv`); corrected, 226.

| Class | Checker row | Count | Skills | Defects |
|---|---|---|---|---|
| in-fence | `SPEC-10a-fence` | 81 occ | 5 | 0 (exempt) |
| cross-skill links | `SPEC-10a-cross` | 90 links / 111 occ | 20 | 90 |
| intra-skill links | `SPEC-10a-intra` | 21 links / 21 occ | 9 | 21 |
| outside link targets | `SPEC-10a-prose` | 13 occ | 6 | 0 |
| — of which self-parent | `SPEC-10a-self-parent` | 3 occ | 1 | 0 (exempt) |

81 + 111 + 21 + 13 = 226. Units matter: 90 is **links**; the same set is 111
`../` *occurrences*, because a `../../` target matches twice — the gap is
exactly 15 × `../../` + 2 × `../../skills/` + 2 × `../../../`. The checker
counts links. The in-fence 81 are working examples (DAB `notebook_path:`
values, TypeScript imports, one deliberate failing `%run`).

The 13 outside link targets (11 plain prose, 2 inside link labels) once counted
3 defects, all `../SKILL.md` in `databricks-metric-views` at
`references/metric-view-advisor.md:18`, `:28`, `:808`. Those 3 are now exempt
under D8 and reported as `SPEC-10a-self-parent`, so **`SPEC-10a-prose` is 0**:
`../SKILL.md` from a `references/` file names its own parent, the path never
leaves the skill directory, and no subset install can break it — which is the
sole rationale for the SPEC-10a class. The row stays must-fix at zero so a
regression is caught.

**SPEC-10b — spec 11 in one skill, corpus 64 across two; checker 64.** 11 is
the count of reference *files*, not of mentions:
`databricks-mlflow-evaluation/SKILL.md` 61 (59 backticked, 2 bold prose at
`:27`-`:28`) and `databricks-app-design/SKILL.md` 3 (backticked, `:27`, `:29`,
`:30`) — a second skill this spec does not name. None are markdown links, so a
`](...)`-only regex finds zero. Two exclusions are load-bearing: a basename in
a link *label* is display text that routes correctly
(`[1-widget-specifications.md#counter](references/1-widget-specifications.md#counter)`)
and counting labels inflates the class to 167; and a basename resolving at the
*skill root* belongs to the root-file finding, or the two classes each report
the other's work as outstanding.

**PD-8 — spec 29 skills, corpus 30 of 32; checker 30**, with a heading regex
that excludes "Troubleshooting". Only `databricks-ml-training` ("Gotchas (the
ones that cost time)", `SKILL.md:252`) and `databricks-pipelines` ("Common
Traps", `SKILL.md:49`) carry a genuine gotchas section. Admitting
"Troubleshooting" credits 5 more (`core`, `genie-agents`, `lakebase`,
`model-serving`, `unstructured-pdf-generation`) and drops the count to 25 — but
that is error recovery after a failure, not an up-front trap list.

**PD-5 — spec 17 skills; checker 228 links across 15 skills.** Different units,
not a different measurement: the audit counted skills carrying the defect, the
checker counts the links to strip, which is what the fix operates on. Only
`databricks-unity-catalog` (29) reproduces exactly. `databricks-pipelines` is 91,
not 103; `spark-structured-streaming` 15, not 22; `apps` and `aibi-dashboards`
19 each, not 21. The audit's "plus 12 others" resolves to 10 — 15 skills total.

**PD-5b — not counted by the audit; checker 12 files in 1 skill.** The audit
described the defect in PD-5's prose ("flatten
`skills/databricks-apps/references/appkit/*.md`") without a count, so it had no
gate. Split out because the unit is **files renamed**, not links stripped, and
because `--only PD-5` reaching zero would otherwise leave the nested directory
in place.

**DESC-1 — spec 5 skills; checker 6 descriptions across 6 skills.** The unit
matches (one description per skill); the population does not. The sixth is
`databricks-genie-agents` at 350 chars — already inside the 300–500 target band,
which is why a length-based screen missed it. It states capability only and
names no condition for firing, the same defect as the other five.

**COMPAT-1 — spec 4 conflicting values; checker 7, blocked.** 7 = **5 excess
shapes + 2 body-vs-frontmatter conflicts**. Six distinct `compatibility` shapes
exist over 32 skills: absent (3), `>= v0.292.0` (2), `>= v0.294.0` (5),
`>= v1.0.0` (20), `>= v1.9.0` (1), `databricks-air` (1). The checker charges one
shape as the target and counts the rest, so 6 − 1 = 5. The audit's 4 counted
only the numeric CLI pins, omitting both `databricks-ai-runtime`'s
`databricks-air` requirement and the 3 skills with no field at all. The 2
conflicts are `databricks-jobs/SKILL.md:44` (body v0.288.0) and
`databricks-python-sdk/SKILL.md:24` (body 0.278.0) against a `>= v1.0.0` pin.

*Checker question, not a corpus defect:* the shape charged as the target is the
first in sort order, and `(absent)` sorts ahead of `Requires…`. As written the
row reaches 0 only if the one surviving shape is "no `compatibility` field at
all". Recorded here rather than fixed — this pass restates counts and must not
move one.

**PD-4 — spec 5 defects in one headline; checker 3 + 19 (blocked) + 3 across
three rows.** The headline conflates three units. `PD-4a` is 3 *occurrences* of
the dead pointer (see below). `PD-4b` is 19 *skills* unrouted from core, which
is neither the audit's "5 children" (core mentions 6) nor its "26 skills declare
parent" (25 do) — it is the difference between them, and it is blocked because
which children belong in core's body is a routing-policy call. `PD-4c` is 3
*files*, which confirms exactly.

**PD-1 / PD-2 / PD-3 — spec 4 skills; checker 3 + 3 + 4.** The per-skill line
and token figures reproduce to the digit (below); only the aggregation differs.
The audit's 4 is the union of the two ceilings, which the checker reports as the
`PD-3` rollup. Because the ceilings bind independently, `databricks-python-sdk`
breaches lines only (4,470 tokens) and `databricks-pipelines` tokens only (258
lines), leaving 3 in each must-fix row. Gating on the rollup would let a skill
that fixed one ceiling read as unresolved.

**NEW-A / NEW-B / NEW-C — not in the audit; checker 6 links / 1 link / 4
files.** `NEW-A`'s 6 are a strict subset of `SPEC-10a-cross`'s 90 — the same
links, counted once for leaving the skill and once for not resolving — so the
cross-skill sweep zeroes both. `NEW-B` is held out of `NEW-A` because its
intended target is unknowable. `NEW-C`'s 4 are also 4 of `PD-6`'s 125.

**Confirmed exact, no reconciliation needed.** PD-1 / PD-2 / PD-3 reproduce to
the digit under `round(len(body) / 4)`: 839/15,683 · 625/4,470 · 525/8,147 ·
258/8,404. The 2,975 / 3,199 resident set reproduces exactly, but only with
YAML-escaped `\"` unescaped, `>-` block scalars folded, and characters summed
across the whole set before a single division; per-skill rounding on that basis
gives 2,974 / 3,199, and leaving block scalars unfolded gives 2,980 / 3,205.
PD-4c's 3 orphans confirm. The dead `databricks-spark-declarative-pipelines`
pointer occurs 3 times, not two (`databricks-docs/SKILL.md:23` and `:52`, plus
`experimental/spark-python-data-source/SKILL.md:145`); and 25 skills declare
`parent: databricks-core`, not 26.

**Aggregate.** must-fix total **568** across 31 skills, heaviest
`databricks-pipelines` (119), `databricks-mlflow-evaluation` (70),
`databricks-apps` (49), `databricks-unity-catalog` (47),
`databricks-spark-structured-streaming` (39). Rollup and advisory rows are not
summed into it.
