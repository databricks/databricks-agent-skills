# Implementation plan

Corpus: 32 skill dirs (30 `skills/`, 2 `experimental/`), 204 `.md` files, 311
files total. Measured at HEAD `50ccd08` + working tree.

**Two of three goals are already green.** `python3 scripts/skills.py validate`
exits 0; `python3 -m unittest discover -s tests -p '*_test.py'` runs **143**
tests (118 pre-existing + 25 new in `tests/audit_check_test.py`), all pass.
`scripts/audit_check.py` now exists and reproduces every number in this plan;
the job is to keep both green while driving it to zero must-fix.

**Sort key:** non-zero count, largest blast radius first (occurrences × skills
touched); within a class, heaviest skill first. Dependency order differs from
priority order — see **Landing order**, which is what you actually execute.

**Constraint that shapes every slice:** upstream cannot merge from this fork.
Each commit must survive cherry-pick into their internal repo as a discrete
unit. One finding class per branch, one PR per branch, no drive-by fixes.
Defects found outside the current branch's scope go to **Deferred**, not into
the diff.

---

## 0. Definitions the checker must pin before any sweep

Six of eight are now **resolved by measurement**. Two remain policy questions
and block their classes.

- **D6 — token/line convention. RESOLVED, exactly.** Strip frontmatter with
  `^---\n.*?\n---\n`; body is everything after. `lines =
  len(body.rstrip("\n").split("\n"))`; `tokens = round(len(body) / 4)`. This
  reproduces all four `specs/02` ceiling figures **exactly** (839/15,683 ·
  625/4,470 · 525/8,147 · 258/8,404). No calibration tolerance is needed —
  require exact match. Floor division instead of `round` is what produces the
  off-by-one drift.
- **D9 — the `../` matcher must exclude `...` ellipsis. RESOLVED. (New — not in
  `specs/02`.)** Naive `\.\./` finds **240** occurrences; **14 are false
  positives** where a literal `...` truncation marker abuts a slash
  (`/Volumes/.../file.csv`, `/subscriptions/.../resourceGroups`,
  `/usr/lib/.../libnccl.so`). Use `(?<![.\w])\.\./` → **226** real occurrences.
  A checker without this over-reports every traversal class and would corrupt
  placeholder paths in 5 skills.
- **D1 — code-fence exemption. RESOLVED as an exemption; the spec text still
  needs amending (see "File as issue").** `specs/01` says "no `../` anywhere in
  a skill directory." Applied literally that flags **81 in-fence traversals
  across 5 skills** (`databricks-jobs` **64**, `databricks-dabs` 8,
  `databricks-apps` 3, `databricks-pipelines` 3,
  `databricks-serverless-migration` 3). **Zero are defects**: 75 are DAB
  relative paths (`notebook_path: ../src/notebooks/extract.py`), which the
  repo's own `skills/databricks-dabs/references/bundle-structure.md:59-66`
  documents as the required form for `resources/*.yml`; 3 are TypeScript
  imports; 3 are a deliberate "before" example of a failing `%run ../../../`.
  None targets a `.md`. The checker must strip fenced blocks (``` and `~~~`,
  indented and language-tagged) before matching.
- **D7 — classify traversals by INTENT, not by resolution. RESOLVED.** If the
  target's first non-`..` segment (after an optional `skills/`) matches a
  sibling skill directory name, classify **cross-skill** regardless of where it
  resolves; flag non-existence separately. Under this rule cross = **90**,
  intra = **21**. Under naive resolution the 6 NEW-A links land in the intra
  bucket, mis-routing the corpus's only broken links into the low-severity
  branch. **This dissolves the old plan's item-2a/item-5 double-count: NEW-A's
  6 are inside cross-90, never inside intra-21.**
- **D2 — bare-basename detection needs three patterns, not one. RESOLVED.**
  A `](...)`-only regex finds **zero** of `databricks-mlflow-evaluation`'s
  defects. Required matchers: (a) markdown link with a `/`-free `.md` target;
  (b) backticked `` `name.md` ``; (c) **bold prose `**Read name.md**`** — form
  (c) exists at `skills/databricks-mlflow-evaluation/SKILL.md:27-28` and is
  missed by both other patterns. Flag when the basename resolves under the
  skill's `references/` or at the skill root.
- **D8 — TOC detection heuristic. RESOLVED (insensitive).** "Has a TOC" = a
  `#{1,6} (Table of Contents|Contents|TOC)` heading in the first 60 lines, **or**
  ≥3 `](#` anchor links in the first 60 lines. Result is stable across variants
  (123–125 of 137). Adopt this and record it in the docstring. 12 files already
  pass — `databricks-jobs` (4), `databricks-mlflow-evaluation` (6),
  `databricks-dbsql` (2) — use them as the house TOC style.
- **D5 — preview-marker definition. STILL BLOCKED, but the audit's number is
  now explained.** Strict parenthetical `(Public Preview|Private Preview|Beta)`
  = **21 / 10 skills** (two independent measurements agree). Broad
  case-insensitive across all `.md` = **85–87 / 15**. Neither is `specs/02`'s
  30/10. Restricting the broad regex to **SKILL.md only** yields **27 / 9** and
  reproduces the audit's named per-skill figures (`lakeflow-connect` 9,
  `pipelines` 6, `zerobus-ingest` 3) — the audit's 30/10 is that count plus a
  **phantom 3 attributed to `databricks-serverless-migration`, which contains
  no preview/beta language at all**. Pick a basis before sweeping.
- **D3 — reference-to-reference definition. RESOLVED.** "Markdown link from a
  file under `references/` to another `.md` resolving inside the same
  `references/` tree, excluding self-links and fenced blocks" → **228 links
  across 15 skills, 69 source files**.
- **D10 — PD-6 counts root-level reference files.** 125 = 121 under
  `references/` + the 4 root-level files (all >100 lines, no TOC). Corpus
  totals 168 + 4 = 172 files, 133 + 4 = 137 over 100 lines. Excluding them is
  the exact blind spot NEW-C describes.
- **D11 — SPEC-10a-cross counts links, not `../` occurrences.** 90 links =
  111 occurrences; a `../../` target matches twice. The 21 gap is exactly
  15 × `../../` + 2 × `../../skills/` + 2 × `../../../`.
- **D12 — SPEC-10b excludes link labels and root-resolving basenames.** A
  basename inside a markdown link *label* is display text and routes
  correctly (`[1-widget-specifications.md#counter](references/1-widget-specifications.md#counter)`);
  counting labels inflates the class from 64 to 167. A basename resolving at
  the skill root is NEW-C, not SPEC-10b, or the two classes each report the
  other's work as outstanding.
- **D13 — PD-8 excludes "Troubleshooting".** 30 lacking is with
  `gotcha|pitfall|common trap`; admitting `troubleshoot` credits 5 more
  skills (core, genie-agents, lakebase, model-serving,
  unstructured-pdf-generation) and gives 25. Only `ml-training` and
  `pipelines` carry a real gotchas section.

**Checker house style — the old plan had this backwards.** `scripts/skills.py`
is a façade; the CLI lives in `scripts/skillsgen/cli.py:main()` (argparse,
positional `mode`). Every one of the 21 existing `check_*` functions returns
`list[str]` and lets the caller print — **do not `raise RuntimeError`**. Follow
`check_skill_frontmatter` (`scripts/skillsgen/validators.py:164`) as the
exemplar and reuse `iter_all_skill_dirs` (`scripts/skillsgen/discovery.py:94`).
`scripts/` contains **no `assert`** today; keep it that way. **Stdlib-only is a
hard constraint** — "the protected CI runner has no pypi"
(`validators.py:21,168`). No PyYAML.

---

## 1. MNT-1a — audit gate — DONE

- **Finding:** MNT-1a
- **Delivered:** `scripts/audit_check.py` (stdlib-only, no `raise`/`assert`,
  house `check_*(repo_root) -> list[str]` style, reuses
  `iter_all_skill_dirs`) and `tests/audit_check_test.py` (25 fixture-based
  tests that pin the *conventions*, not the corpus counts, so they stay
  green as findings are swept).
- **Usage:** `python3 scripts/audit_check.py [--only ID[,ID...]] [--details]`.
  Exit 0 when every selected must-fix finding is at zero; advisory/blocked/
  rollup findings gate the exit status only when named explicitly in
  `--only`; unknown ID exits 2. Verified: a corpus with the finding at zero
  exits 0.
- **Not wired** into `scripts/skills.py validate` — that stays item 16
  (MNT-1b), for the last sweep PR.
- **Landed** on branch `feature/claude-skill-agent-loop` (not the planned
  `ralph/audit-check-bootstrap` — the loop pushes this branch).

**Phase 1 close runs off `ralph/phase1-base`.** The earlier loops left two
divergent heads — `ralph/spec-10a-intra` (cross + intra, off `2b9807a`) and
`ralph/pd-5-rest` (PD-5 + PD-5b, off `bc9ddb7`) — so no single branch carried
all the completed work and no two counts were comparable. `ralph/phase1-base`
is `ralph/pd-5-rest` plus the checker commit `20ac968` (GEN-1 as a freshness
check) plus the SPEC-10a-cross sweep `32c297d`, cherry-picked in that order.
The intra sweep was NOT carried over: on this base the count is **19**, not the
21 the older branch swept, because the PD-5b appkit flatten already cleared 2.
Redoing it against the live population is branch `ralph/spec-10a-remainder`.
Conflict resolutions were semantic, not textual — where PD-5 and SPEC-10a-cross
edited the same line, the cross fix (drop the sibling path, name the skill) and
the PD-5 fix (strip the intra-`references/` link to a plain name) were both
applied. Every remaining branch chains off this base.

**Per-finding count table — the live baseline every future loop measures
against:**

| ID | Severity | Count |
|---|---|---|
| PD-6 | must-fix | 121 (was 125; the NEW-C branch shipped 4 TOCs) |
| PD-5 | must-fix | **0 — DONE** (was 228) |
| PD-5b | must-fix | **0 — DONE** (was 12) |
| SPEC-10a-cross | must-fix | **0 — DONE** (was 90) |
| SPEC-10a-intra | must-fix | **0 — DONE** (was 19; 21 at audit, the PD-5b flatten cleared 2) |
| SPEC-10a-prose | must-fix | 0 (the 3 moved to `SPEC-10a-self-parent`, `2b9807a`) |
| SPEC-10b | must-fix | **0 — DONE** (was 64) |
| NEW-A | must-fix | 0 |
| NEW-C | must-fix | **0 — DONE** (was 4) |
| PD-4a | must-fix | **0 — DONE** (was 3) |
| PD-4c | must-fix | **0 — DONE** (was 3; the PD-5 sweep cleared all 3) |
| PD-1 | must-fix | 3 |
| PD-2 | must-fix | 3 |
| DESC-1 | must-fix | **0 — DONE** (was 6) |
| PD-3 | rollup | 4 |
| PD-4b | blocked | 19 |
| TOK-5 | blocked | 21 |
| COMPAT-1 | blocked | 7 |
| SPEC-10a-fence | advisory | 81 |
| SPEC-10a-self-parent | advisory | 3 |
| NEW-B | advisory | 0 (was 1; the PD-5 strip turned the link into prose) |
| PD-8 | advisory | 30 |
| MNT-6 | advisory | 1 |

must-fix total **127** (rollup/advisory not summed); resident set **3,347 stable /
3,571 all-in** (was 2,975 / 3,199; the DESC-1 rewrite added 372 tokens).

---

## 2. PD-6 — missing reference TOCs — 125 → 0

- **Finding:** PD-6
- **Paths:** 125 files across **26 skills**. Heaviest: `skills/databricks-apps`
  14, `skills/databricks-pipelines` 13,
  `skills/databricks-spark-structured-streaming` 11,
  `skills/databricks-serverless-migration` 8,
  `experimental/spark-python-data-source` 8, `skills/databricks-lakebase` 7,
  `skills/databricks-unity-catalog` 7, then 19 skills with 1–5.
- **Count:** **125 of 137** reference files over 100 lines lack a TOC → **0**
- **Backpressure:** `python3 scripts/audit_check.py --only PD-6` → 0

Largest TOC-less files, start here:
`skills/databricks-unity-catalog/references/5-system-tables.md` (1,043 lines),
`skills/databricks-aibi-dashboards/references/4-examples.md` (1,021),
`skills/databricks-mlflow-evaluation/references/patterns-datasets.md` (871),
`skills/databricks-metric-views/references/metric-view-advisor.md` (822 lines /
59,852 bytes — largest by bytes in the repo).

**Lands last of the link/structure sweeps.** The blocking overlap is now
discharged: 56 of the 125 files were also PD-5 sources, and PD-5 is at 0, so a
TOC written today will not be regenerated by a later link sweep. The one
measured overlap left is `intra ∩ PD-6 = 13 files` — sequence PD-6 after
SPEC-10a. Split into ≥3 commits by skill so a 125-file diff stays
cherry-pickable.

---

## 3. PD-5 — reference-to-reference links — 228 → 0 — **DONE**

> **Swept across all 15 skills.** `ralph/pd-5-pipelines` took
> `databricks-pipelines` (91, `4fcb43e`); `ralph/pd-5-rest` took the other 14
> in four batches (`70fd794` unity-catalog 29 + aibi-dashboards 19; `6fe7086`
> apps 19 with the PD-5b flatten; `7432b80` streaming 15 + metric-views 13 +
> lakebase 9 + ml-training 8; `ec4c42e` the last seven, 25). Each content
> commit is paired with a `chore: self-heal bundle from source`.
>
> **PD-4c fell out with it — 3 → 0, no separate branch needed.** All three
> orphans (`pipelines/references/{python,sql}-basics.md`,
> `lakebase/references/medallion-from-cdc.md`) were reachable only through a
> second hop, so the PD-5 defect and the orphan were one defect. Each is now
> linked from its own `SKILL.md` with a stated read condition.
>
> **Side effects, all downward:** `SPEC-10a-intra` 21 → 19 (the PD-5b flatten
> turned two `../platform-guide.md` links into sibling links) and advisory
> `NEW-B` 1 → 0 (the strip turned the unresolvable `plugin-contracts.md` link
> into prose; the maintainer question of what it meant is still open, see
> **File as issue**). No count increased. must-fix 475 → 323.

### Sweep recipe (validated across 15 skills, 228 links)

Keep this — PD-6 and the SPEC-10a sweeps reuse the same machinery.

1. **Substitution:** replace `[label](target.md#anchor)` with the plain text
   `target#anchor` — basename minus `.md`, anchor kept. Dropping the anchor
   loses navigation; keeping the label loses the pointer when the label is a
   format name (`[JSON](options-json.md)` → `options-json` reads correctly,
   `JSON` does not).
2. **Skip fenced code.** The checker exempts it (D1) and the fenced paths are
   working examples. A fence-blind regex corrupts them silently. Mirror
   `strip_fences` rather than re-deriving it — a *line mask* over the raw text
   edits in place while matching the checker's line numbering exactly.
3. **`.md` in reference-file prose is safe** — `check_spec_10b` scans
   `SKILL.md` only, so stripping to a bare basename there cannot raise
   SPEC-10b. Dropping the extension anyway costs nothing and survives a
   future widening of that check.
4. **Then route from SKILL.md.** Compare `references/*.md` against SKILL.md
   text; every file the sweep un-links needs a direct link *with a stated read
   condition*. 3 of 15 skills needed an edit here — and each of those files was
   a PD-4c orphan. Expect the two findings to coincide exactly.
5. **Read every substituted line in context.** The mechanical pass demotes
   product names to filenames whenever the link *label* was the name of a
   thing rather than a description of a file. Four sites across the sweep:
   `pipelines/streaming-patterns.md:94` (Real-Time Mode),
   `unity-catalog/3-securables-ddl.md:57` (external location),
   `aibi-dashboards/1-widget-specifications.md:401` (Heatmap, Choropleth Map),
   and all six `execution-compute` "Switch to **[Serverless Job](…)** when:"
   lines. Fix shape: keep the name, parenthesise the pointer —
   `**Serverless Job** (2-serverless-job)`.
6. **Grammar breaks when a backticked filename becomes a bare word.**
   "The parent skill's `patterns.md` shows" → "…patterns shows"
   (`metric-view-advisor.md:758`). Same read-in-context pass catches it.

**Bundle:** any `skills/**` content change stales `plugins/**` (a generated
copy), so `skills.py validate` and `test_repo_bundle_is_canonical` fail until
`scripts/skills.py generate` runs. GEN-1 forbids the branch touching
`plugins/**`, so the two cannot both be satisfied in one commit. Resolution
used here, matching upstream (`50ccd08`, `76d4fdc`): **content commit first,
then a separate `chore: self-heal bundle from source`**. The bundle commit is
4 × the content commit's file count, counting only files under `skills/` —
`experimental/` has no bundle copy (the bundle ships the 30 stable skills).
Do not fold the bundle into the content commit — it buries the reviewable diff.

### 3a. PD-5b — flatten `references/appkit/` — 12 files → 0 — **DONE**

`6fe7086`. `skills/databricks-apps/references/appkit/*.md` →
`references/appkit-*.md`; `appkit-sdk.md` keeps its name rather than becoming
`appkit-appkit-sdk.md`. The repo's only two-level reference dir is gone.

**A flatten is not just a rename — three sets of links move with it**, and
missing any one of them raises `NEW-A`:

- 20 links in the owning `SKILL.md`.
- **Inbound cross-skill paths**, which resolve today and dangle after the move:
  `databricks-model-serving/SKILL.md:220` and
  `databricks-lakebase/references/{pgvector,off-platform,connectivity}.md`.
  Repoint them, keep their `../` form — the traversal is SPEC-10a-cross's
  defect to fix, and rewriting it here would hide it.
- **Outbound paths that change depth**: `../../../databricks-lakebase/…` in
  `appkit-lakebase.md` became `../../`.

Do the rename *before* the PD-5 strip: the strip resolves link targets to
decide what to rewrite, so it needs the post-move paths to be correct.
`scripts/skills.py generate` prunes the stale bundle directories on its own.

---

## 4. SPEC-10a-cross — cross-skill `../` traversal — DONE

- **Finding:** SPEC-10a-cross (includes NEW-A) — **DONE**, 90 → 0 and 6 → 0.
- **Landed** on branch `ralph/spec-10a-cross` (branched off
  `feature/claude-skill-agent-loop`, which owns MNT-1a — one finding class per
  branch).
- **Scope:** 90 links across 26 files in 20 skills; diff was 26 files, 87
  changed lines, zero net line change, plus 104 regenerated bundle mirrors
  (26 × 4 provider targets). `manifest.json` did NOT change (no file paths
  moved).
- **Adopted convention — a rule for future branches:** a cross-skill pointer
  becomes prose naming the sibling skill in backticks plus the word "skill"
  (the house form already in-tree, e.g. "see the `databricks-lakebase`
  skill"). The sibling's file path is DROPPED ENTIRELY, not rewritten — a
  cross-skill path in prose is still a cross-skill path, just one no
  validator can see, so it rots silently. Where the link pointed at a
  reference file in the sibling, a descriptive label replaces the path ("its
  Lakebase Guide", "the `databricks-spark-structured-streaming` skill's RTM
  reference"), with labels chosen to be greppable in the sibling's own
  SKILL.md.
- **Consequence worth recording:** this DECOUPLES the appkit flatten. Because
  no prose now carries a `references/appkit/...` path, PD-5b (item 3a) no
  longer has to touch
  `skills/databricks-lakebase/references/{off-platform,pgvector,connectivity}.md`
  or `skills/databricks-model-serving/SKILL.md`.
- **Mechanical shape** used for the ~70 routine sites:
  `**[databricks-x](../databricks-x/SKILL.md)**` -> ``**`databricks-x`**``,
  emphasis preserved.
- **Backpressure:** `python3 scripts/audit_check.py --only SPEC-10a-cross,NEW-A`
  → 0.

---

## 5. SPEC-10b — bare-basename references — 64 → 0 — DONE

- **Finding:** SPEC-10b — **DONE**, 64 → 0.
- **Landed** on branch `ralph/spec-10b-basenames`, off `ralph/phase1-base`.
- **Scope:** `skills/databricks-mlflow-evaluation/SKILL.md` 61 (59 backticked +
  2 bold-prose at `:27`-`:28`), `skills/databricks-app-design/SKILL.md` 3
  (backticked, `:27`, `:29`, `:30`). Zero were markdown links.
- **Fix applied uniformly:** keep the existing shape, prefix the path —
  `` `patterns-datasets.md` `` → `` `references/patterns-datasets.md` ``,
  `**Read GOTCHAS.md**` → `**Read references/GOTCHAS.md**`. Links were NOT
  promoted to markdown link syntax: 52 of the 61 sit in table cells whose
  columns are the repo's best routing, and rewriting them would have churned
  the tables for no gate.
- **Byte-preservation held.** The diff is 61 + 3 changed lines, each a pure
  prefix insertion; the eight numbered workflow tables are otherwise untouched.
  `app-design` lines 14–16 already carried the prefix, so the fix made that
  file internally consistent rather than introducing a new form.
- **No product-name demotion** (the PD-5 sweep's failure mode): this class
  substitutes in the opposite direction — filename → longer path — and all 64
  labels named files, never things. Diff read line by line to confirm.
- **Backpressure:** `audit_check.py --only SPEC-10b` → 0; unscoped run moved
  exactly one row (64 → 0), must-fix total 227 → **163**; `skills.py validate`
  → 0; 149 tests pass.

---

## 6. TOK-5 — uncontained preview/beta markers — 21 → 0 — BLOCKED on D5

- **Finding:** TOK-5
- **Paths (strict basis):** `skills/databricks-pipelines` 8,
  `skills/databricks-zerobus-ingest` 3, `skills/databricks-iceberg` 2,
  `skills/databricks-ml-training` 2, then 6 skills with 1
  (`apps`, `apps-python`, `lakebase`, `lakeflow-connect`, `mlflow-evaluation`,
  `spark-structured-streaming`)
- **Count:** **21 across 10 skills** (strict) → 0. Broad basis: 85–87 / 15.
- **Backpressure:** `python3 scripts/audit_check.py --only TOK-5` → 0; raw
  floor `grep -rEo '\((Public Preview|Private Preview|Beta)\)' skills/
  experimental/ --include='*.md' | wc -l` → 0 (currently 21)

**BLOCKED until D5 is chosen and written into the checker's docstring.**
Consolidate into a per-skill dated status table or an "old patterns" section.
Do not delete the information.

---

## 7. SPEC-10a-intra — `../` inside a skill — 19 → 0 — DONE

- **Finding:** SPEC-10a-intra — **DONE**, 19 → 0.
- **Landed** on branch `ralph/spec-10a-remainder`, off `ralph/spec-10b-basenames`.
- **Population was 19, not the audit's 21.** The PD-5b appkit flatten already
  cleared the 2 `references/appkit/{jobs,model-serving}.md → ../platform-guide.md`
  links, exactly as this plan predicted. All 19 survivors were the same shape:
  a markdown link from a `references/` file to its own skill's `SKILL.md`.
- **Convention (re-landed from `e9c265c`, unchanged):** drop the link, keep the
  name — `[SKILL.md](../SKILL.md)` → `` `SKILL.md` ``; where the anchor carried
  routing, keep it as `` `SKILL.md` § "Exact Heading" ``. There is no `../`-free
  markdown path from `references/x.md` to its own `SKILL.md`: `](SKILL.md)`
  resolves to `references/SKILL.md` and would dangle as NEW-A. Rewriting is
  impossible, so the link is dropped rather than repaired.
- **18 of the 19 sites matched `e9c265c` byte-for-byte.** The 19th
  (`databricks-lakeflow-connect/references/4-ingestion-decision-tree.md:22`)
  differed only because the PD-5 sweep had already stripped a neighbouring link
  on the same line; the `SKILL.md` substitution there is identical.
- **All 8 quoted `§` headings verified present** in their target `SKILL.md`.
  A mis-quoted heading is a silent routing defect and no checker row sees it.
- **No product-name demotion.** Four labels named a *thing* rather than the
  file (`Overview table`, `Widget Index`, `CLI Execution`,
  `Failure Reporting Protocol`); each survives as prose or as a `§` clause.
- **Backpressure:** `audit_check.py --only SPEC-10a-intra` → 0; unscoped run
  moved exactly one row, must-fix 163 → **144**; `skills.py validate` → 0;
  149 tests pass.

---

## 8. PD-4b — regenerate `databricks-core`'s routing — 5 → full graph — BLOCKED

- **Finding:** PD-4b
- **Path:** `skills/databricks-core/SKILL.md:13-20`
- **Count:** routes to **5** children (`jobs`, `pipelines`, `apps`, `lakebase`,
  `model-serving`); **25** skills declare `parent: databricks-core`; **19** of
  them are not mentioned anywhere in the file in any form → target: every skill
  reachable from the routing list ∪ the parent graph, with no skill in one and
  not the other
- **Backpressure:** `python3 scripts/audit_check.py --only PD-4b` → 0

**The parent graph is 25, not `specs/02`'s 26.** Full shape: 25 ×
`parent: databricks-core`; 1 × `parent: databricks-apps`
(`skills/databricks-app-design`); **6 with no `parent` at all** —
`skills/databricks-core` (correct, it is the root),
`skills/databricks-dabs`, `skills/databricks-genie-agents`,
`skills/databricks-zerobus-ingest`, `experimental/databricks-ai-runtime`,
`experimental/spark-python-data-source`. 25 + 1 + 6 = 32. ✓

`databricks-data-discovery` is named in prose at lines 22–26 but is absent from
the bulleted list — a 20th gap of a different kind.

**BLOCKED:** naive regeneration from the parent graph silently drops 4 stable
skills. Unblock by deciding parents for `dabs`, `genie-agents`,
`zerobus-ingest`, and the `parent: databricks-apps` outlier — a maintainer
call, filed below. Do not guess parents.

---

## 9. NEW-C — reference files at the skill root — 4 files / 12 links → 0 — DONE

- **Finding:** NEW-C — **DONE**, 4 → 0.
- **Landed** on branch `ralph/new-c-root-refs`, off `ralph/pd-4-routing`, in
  two commits: the move, then the four TOCs that finish the moved files.
- **Moved:** `databricks-core/{databricks-cli-auth,databricks-cli-install,
  manual-data-exploration}.md` and
  `experimental/databricks-ai-runtime/docker-images.md` → each skill's new
  `references/` directory (neither skill had one).
- **12 inbound links** re-prefixed, exactly as this plan predicted: 11 in
  `databricks-core/SKILL.md`, 1 in `databricks-ai-runtime/SKILL.md:33`.
- **Two pointers outside the skills tree** also had to move, neither of which
  the plan had recorded:
  - `commands/setup.md:16` — hand-written command source (the rendered copies
    under `plugins/*/commands/` follow from `generate`).
  - `references/manual-data-exploration.md:90` linked `databricks-cli-auth.md`.
    Root-to-root before the move, **reference-to-reference after it** — this
    branch would have regressed PD-5 from 0 to 1. Fixed in the same commit
    under the house PD-5 shape (keep the name, parenthesise the pointer). The
    label named a thing, so "CLI Authentication Guide" survives.
- **PD-6 accounting.** The move was **population-neutral** — PD-6 held at 125,
  because D10 already counts root-level reference files; that is the whole
  point of D10. The general expectation that a relocating branch pushes PD-6 up
  then back down does **not** apply to NEW-C. The TOC commit then took PD-6
  **125 → 121**, exactly the four files this branch moved.
- **Anchors verified.** All 57 generated anchor links resolve against a
  GitHub-style derivation of the real headings; fenced blocks were masked first
  so a `# comment` inside a bash fence could not become a phantom entry.
- **Backpressure:** `audit_check.py --only NEW-C` → 0; must-fix 141 → **133**;
  `skills.py validate` → 0; `manifest.json` changed (paths moved) and is staged
  with the bundle; 149 tests pass.

---

## 10. Compatibility pin — 4 pins + 3 absent + 1 other-CLI → 1 — BLOCKED

- **Finding:** Compatibility pin inconsistency — the checker assigns this
  finding the ID **COMPAT-1** (the plan and `specs/02` name it in prose only)
- **Paths:** frontmatter across 28 skills, plus **7 skills hardcoding a CLI
  version in the body**: `skills/databricks-core/SKILL.md:31`,
  `skills/databricks-agent-bricks/SKILL.md:60`,
  `skills/databricks-data-discovery/SKILL.md:61,78,121`,
  `skills/databricks-jobs/SKILL.md:44`,
  `skills/databricks-lakebase/SKILL.md:346`,
  `skills/databricks-lakeflow-connect/SKILL.md:96`,
  `skills/databricks-python-sdk/SKILL.md:24`,
  `skills/databricks-unity-catalog/SKILL.md:17`
- **Count:** `>= v1.0.0` (20), `>= v0.294.0` (5), `>= v0.292.0` (2),
  `>= v1.9.0` (1); **3 with no `compatibility`** (`databricks-app-design`,
  `databricks-dabs`, `databricks-vector-search`); **1 pinning a different CLI**
  (`experimental/databricks-ai-runtime` → `databricks-air`, legitimately
  different). **6 distinct CLI version literals** once bodies are counted →
  target 1, or per-skill values individually justified. **COMPAT-1 totals
  7:** 5 excess shapes (6 distinct — 4 CLI pins + `databricks-air` +
  "(absent)" — minus the target of 1) plus 2 body-vs-frontmatter
  contradictions (`databricks-jobs`, `databricks-python-sdk`)
- **Backpressure:** `grep -h '^compatibility:' skills/*/SKILL.md
  experimental/*/SKILL.md | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | sort -u | wc -l`
  → 1, and `python3 scripts/skills.py validate; echo $?` → 0

**BLOCKED on a verified current Databricks CLI version. Do not guess a value.**
Plan it, then stop. Derive from one constant in `scripts/skillsgen/`.

**Two skills contradict themselves** (new, beyond `specs/02`):
`databricks-jobs` pins `>= v1.0.0` in frontmatter but says `>= v0.288.0` at
line 44; `databricks-python-sdk` pins `>= v1.0.0` in frontmatter but states
`>= 0.278.0` in the body at **both** `SKILL.md:24` and `:89` — the checker
flags line 24 only, because line 89 ("# Check version (should be >=
0.278.0)") does not name the CLI. Those two are internally inconsistent
regardless of which global value wins, and can be fixed independently of the
blocked decision.

---

## 11. PD-1 / PD-2 / PD-3 — SKILL.md ceiling breaches — 4 → 0

- **Finding:** PD-1 / PD-2 / PD-3
- **Count:** 4 skills over a ceiling → **0**
- **Backpressure:** `python3 scripts/audit_check.py --only PD-1,PD-2,PD-3` → 0,
  plus a per-skill character-total delta ≤2% printed by the checker

| Path | Lines | Tokens | Breach | Split |
|---|---|---|---|---|
| `skills/databricks-serverless-migration/SKILL.md` | 839 | 15,683 | both | "Quick Fixes Reference" → `references/quick-fixes.md`; Step 2 notebook transcripts → `references/analysis-output-examples.md` |
| `skills/databricks-python-sdk/SKILL.md` | 625 | 4,470 | LINES only | split by SDK object family (clusters, jobs, unity catalog, serving) |
| `skills/databricks-aibi-dashboards/SKILL.md` | 525 | 8,147 | both | widget-spec detail into existing `references/` |
| `skills/databricks-pipelines/SKILL.md` | 258 | 8,404 | TOKENS only | decision tree + Common Traps → `references/` |

These are `specs/02`'s figures reproduced **exactly** under D6 — the previous
plan's competing numbers (838/15,784 · 613/4,458 · 516/8,175 · 257/8,517) were
a measurement error, not convention drift. `databricks-pipelines` passes lines
and fails tokens: mean line 130 chars. Both ceilings bind independently.
Closest non-breaching skill is `skills/databricks-apps` at 4,946 tokens — a
54-token margin, so any content moved *into* it will breach.

**Move content verbatim.** Do not summarise. Leave routing pointers with load
conditions. One commit per skill, heaviest first. **Depends on items 2 and 3** —
new reference files must ship with TOCs and without second hops.

---

## 12. DESC-1 / DESC-3 — descriptions without trigger conditions — 6 → 0 — DONE

- **Finding:** DESC-1 — **DONE**, 6 → 0.
- **Landed** on branch `ralph/desc-1-triggers`, off `ralph/new-c-root-refs`.
- **Shape applied to all six**, from the `databricks-data-discovery` model:
  what the skill does → `Use this skill when the user asks to '<literal
  phrasing>'…` → `Do not use for … (<named sibling>)`. Third person; the
  quoted phrasings are what a user actually types, not paraphrases of the
  body.
- **Sibling named in every one**, which is what makes the clause load-bearing:

  | Skill | chars (was → now) | Yields to |
  |---|---|---|
  | `databricks-agent-bricks` | 122 → 495 | `genie-agents`, `ml-training` |
  | `databricks-vector-search` | 133 → 488 | `lakebase` (pgvector), `ai-functions` |
  | `databricks-execution-compute` | 173 → 497 | `dabs` (a `databricks.yml` exists), `jobs` |
  | `databricks-unstructured-pdf-generation` | 253 → 481 | `synthetic-data-gen` |
  | `databricks-genie-agents` | 350 → 498 | `data-discovery` (Genie One) |
  | `databricks-ai-functions` | 415 → 476 | `model-serving`, `vector-search` |

- **All six land inside the 300–500 target band** (476–498), well under the
  1,024 hard cap. Four first drafts came in at 504–581 and were tightened
  rather than allowed to run long.
- **`databricks-ai-functions` keeps all 12 function names.** They are literal
  trigger tokens a user types (`ai_extract`, `ai_parse_document`, …), so they
  were treated as trigger content and the surrounding prose was cut instead.
- **Resident-set delta against the 2,975-token stable baseline:
  2,975 → 3,347 stable (+372 tokens, +12.5%); 3,199 → 3,571 all-in (+372).**
  All six are stable skills, so both figures move by the same amount. The
  1,477 added characters ÷ 4 = 369 predicted; the 3-token gap is the single
  division over the summed corpus, exactly as D6 specifies.
- **Backpressure:** `audit_check.py --only DESC-1` → 0; must-fix 133 → **127**;
  exactly one row moved; `skills.py validate` → 0; 149 tests pass.

---

## 13. PD-4a — dead skill pointer — 3 → 0 — DONE

- **Finding:** PD-4a — **DONE**, 3 → 0.
- **Landed** on branch `ralph/pd-4-routing`, off `ralph/spec-10a-remainder`,
  in two commits: the pointer swap, then the terminology settlement.
- **Sites:** `databricks-docs/SKILL.md:23`, `:52`,
  `experimental/spark-python-data-source/SKILL.md:145`. Name swapped only;
  surrounding prose byte-preserved.
- **Terminology settled in `databricks-docs`** using the canonical name from
  the skill that owns the product rather than one invented here:
  `databricks-pipelines` titles itself "Lakeflow Spark Declarative Pipelines"
  and records the alias set at its `SKILL.md:51`. The legacy names now appear
  exactly once, on the Related Skills routing line where a reader who knows
  the product as "DLT" needs to recognise it. `:42` was left alone — it
  enumerates llms.txt documentation categories, not one product under three
  names.
- **Backpressure:** `audit_check.py --only PD-4a` → 0; unscoped run moved
  exactly one row, must-fix 144 → **141**; the terminology commit moved no row
  by design; `skills.py validate` → 0.

---

## 14. PD-4c — orphan reference files — 3 → 0 — **DONE**

Cleared inside item 3; **no separate branch was needed**. The prediction below
held exactly: none of the three was a true dead end, each was reachable one hop
away from a reference file that *is* linked from `SKILL.md`, and the PD-5 strip
removed that hop. All three were linked from their owning `SKILL.md` with a
stated read condition in the same commit that stripped them:

- `pipelines/references/{python,sql}-basics.md` → a "Language primers" group in
  the Reference Index (`4fcb43e`)
- `lakebase/references/medallion-from-cdc.md` → sixth entry in the Reference
  docs list, `SKILL.md:50` (`7432b80`)

None was deleted. **Generalise:** a PD-4c orphan and a PD-5 second hop are the
same defect seen from two sides — whenever a sweep un-links a reference,
re-route it in the same commit rather than filing it.

---

## 15. SPEC-10a-prose — `../` in non-link prose — 3 → 0

- **Finding:** SPEC-10a-prose
- **Path:** `skills/databricks-metric-views/references/metric-view-advisor.md`
  lines **18, 28, 808** — backticked `` `../SKILL.md` `` in narrative text
- **Count:** **3 → 0** (not the 19 the previous plan claimed)
- **Backpressure:** `python3 scripts/audit_check.py --only SPEC-10a-prose` → 0

Of 13 non-link, non-fence traversals after the D9 ellipsis correction, only
these 3 are defects. **8 are legitimate documentation *about* `../`** and must
not be touched — `databricks-dabs/references/bundle-structure.md:62 (×2),65,247`
and `deploy-and-run.md:95` (the DAB path-resolution rule),
`databricks-dbsql/references/ai-functions.md:775` ("Cannot contain directory
traversal (`../`)"), `databricks-apps/references/appkit-files.md:323` (an error
message), `databricks-serverless-migration/SKILL.md:229` (a `%run ../path`
warning). The remaining **2** are link *text* in
`databricks-pipelines/references/real-time-mode.md:5,153` and disappear when
item 4 rewrites those links.

---

## 16. MNT-1b — regression guards in `scripts/skillsgen/validators.py`

- **Finding:** MNT-1b
- **Paths:** `scripts/skillsgen/validators.py`, `scripts/skillsgen/cli.py`,
  `tests/skills_generator_test.py`
- **Count:** 0 guards → 1 per class already at zero
- **Backpressure:** `python3 scripts/skills.py validate; echo $?` → 0 and
  `python3 -m unittest discover -s tests -p '*_test.py'` → all pass, with new
  tests added

**Last sweep PR only.** Add `check_skill_links` / `check_skill_traversal` in the
file's existing style (`list[str]` return, no raise). Two things make early
wiring fail: the `self.assertEqual(skills.check_x(_REPO), [])` test pattern, and
adding the call to `cli.py`'s `validate` sequence, which makes `validate` exit 1
and breaks per-PR gate #2 for every other branch.

---

## 17. GC-1 / GC-8 — author `databricks-genie-code` — 0 → 1

- **Finding:** GC-1 / GC-8
- **Paths:** `skills/databricks-genie-code/{SKILL.md,references/practice-guide.md,references/troubleshooting.md}`
  plus the `metaplugin/plugin.meta.json` entry, then `python3
  scripts/skills.py generate`
- **Count:** 0 skills → **1**
- **Backpressure:** `python3 scripts/audit_check.py` → 0 must-fix **including**
  the new skill; `python3 scripts/skills.py validate; echo $?` → 0; present in
  all four marketplace catalogs after `generate`, with no drift

Authoring task, not a sweep. Follow `specs/03-genie-code-skill.md` literally:
two H2s in order, three-way Genie disambiguation in the description, the two
named exclusions from the practice guide, no date literals, no `entrada.ai`
citation. **Do last, on its own branch** — it must pass a checker already at
zero everywhere else, or its failures are indistinguishable from the backlog.

Note the skeleton asymmetry: **0 of the 32 existing skills** match `specs/01`'s
two-H2 skeleton, and `specs/01` explicitly scopes that rule to newly authored
skills ("Existing skills are not restructured wholesale"). The checker must
apply the H2 rule to this skill only — a corpus-wide H2 gate would report 32
false must-fixes.

---

## 18. PD-8 / MNT-6 — gotchas + script execution intent — batch last

- **Finding:** PD-8 / MNT-6
- **Paths:** PD-8 — **30** SKILL.md files lack a gotchas-style heading (only
  `skills/databricks-ml-training` and `skills/databricks-pipelines` have one;
  `specs/02` says 29). MNT-6 —
  `skills/databricks-synthetic-data-gen/scripts/generate_synthetic_data.py`;
  confirmed these two skills are the only ones bundling `scripts/`, but only
  this one's SKILL.md fails to state run-vs-read intent
- **Count:** 30 → 0; **1** → 0 (not 2 —
  `skills/databricks-unstructured-pdf-generation/scripts/pdf_generator.py`
  DOES state run intent: `SKILL.md:17` names the script, `:43` gives the
  literal `python <SKILL_ROOT>/scripts/pdf_generator.py convert ...`
  invocation, `:124` a manifest row, `:126` a recreate-if-absent fallback.
  Only `databricks-synthetic-data-gen` lacks intent, and its
  `generate_synthetic_data.py` is referenced nowhere in the skill at all —
  an orphan script, arguably a different defect.)
- **Backpressure:** not a must-fix gate — do not let it block the definition of
  done. `python3 scripts/audit_check.py --only PD-8,MNT-6` reported as advisory.

---

## Landing order (dependency-forced — differs from priority order)

Priority ranks by blast radius; execution must respect file overlap. Measured
overlap: PD-5 ∩ PD-6 = **56 files**; cross ∩ PD-5 = 6; intra ∩ PD-5 = 8;
intra ∩ PD-6 = 13; cross ∩ intra = 3. **Every PD-5 overlap is now spent** —
steps 7 and 7b are done, so only `intra ∩ PD-6 = 13` and `cross ∩ intra = 3`
still constrain the order.

| Step | Branch | Item | Count → target |
|---|---|---|---|
| 1 | `feature/claude-skill-agent-loop` | 1 · MNT-1a | DONE |
| 2 | `ralph/spec-10a-cross` | 4 · SPEC-10a-cross + NEW-A | DONE (90 → 0) |
| 3 | `ralph/spec-10a-remainder` | 7 · SPEC-10a-intra | DONE (19 → 0) |
| 4 | `ralph/spec-10a-prose` | 15 · SPEC-10a-prose | already 0 — regression guard only |
| 5 | `ralph/spec-10b-basenames` | 5 · SPEC-10b | DONE (64 → 0) |
| 6 | `ralph/new-c-root-refs` | 9 · NEW-C (+ `generate`) | DONE (4 → 0) |
| 7 | `ralph/pd-5-pipelines` **done** | 3 · PD-5 (pipelines only) | 228 → 137; PD-4c 3 → 1 |
| 7b | `ralph/pd-5-rest` **done** | 3 + 3a · PD-5 (14 skills), PD-5b | 137 → 0; 12 → 0; PD-4c 1 → 0 |
| 8 | ~~`ralph/pd-4c-orphans`~~ **absorbed by 7 + 7b** | 14 · PD-4c | 3 → 0, done |
| 9 | `ralph/pd-6-toc` | 2 · PD-6 (≥3 commits) | 125 → 0 |
| 10 | `ralph/pd-1-ceilings` | 11 · PD-1/2/3 (1 commit each) | 4 → 0 |
| 11 | `ralph/pd-4-routing` | 13 · PD-4a | DONE (3 → 0) |
| 12 | `ralph/desc-1-triggers` | 12 · DESC-1/3 | DONE (6 → 0) |
| 13 | `ralph/tok-5-preview` | 6 · TOK-5 — **BLOCKED on D5** | 21 → 0 |
| 14 | `ralph/pd-4b-core-routing` | 8 · PD-4b — **BLOCKED** | 5 → full graph |
| 15 | `ralph/compat-pin` | 10 · Compatibility — **BLOCKED** | 8 shapes → 1 |
| 16 | `ralph/mnt-1b-validators` | 16 · MNT-1b | last sweep only |
| 17 | `ralph/genie-code-skill` | 17 · GC-1/8 | 0 → 1 |
| 18 | `ralph/pd-8-gotchas` | 18 · PD-8/MNT-6 | advisory |

Steps 11–12 are order-independent of 2–10 (disjoint files) and may run in
parallel. Steps 13–15 are unblocked only by a maintainer decision.

### Per-PR checklist (all branches)

1. `python3 scripts/audit_check.py --only <ID>` → 0
2. `python3 scripts/skills.py validate; echo $?` → 0
3. `python3 -m unittest discover -s tests -p '*_test.py'` → 143 pass
4. `git status` clean under `plugins/`, `manifest.json`, `*/marketplace.json`
   (generated — regenerate with `scripts/skills.py generate`, never hand-edit)
5. Single concern; commit message names the finding ID and the before→after count

---

## Measurement disagreements with `specs/02` (record, do not silently adopt)

| Finding | `specs/02` claims | Measured | Nature |
|---|---|---|---|
| SPEC-10a | 19 skills, 128 occ | cross **90**/20 · intra **21**/9 · prose **13**/6 (only **3** are defects) · fence **81**/5 (**0** defects) | audit conflated 4 classes and counted links only; missed `databricks-jobs` (64 in-fence, largest holder, unlisted) |
| SPEC-10a-cross occ (D11) | — | 90 links = **111** occurrences | `../../` matches twice; 21-occurrence gap = 15 × `../../` + 2 × `../../skills/` + 2 × `../../../`; new |
| SPEC-10a ellipsis | — | naive `\.\./` = 240 vs **226** real | **14 false positives** from `.../` truncation markers; new |
| SPEC-10b | 11 | **64 mentions across 2 skills** — 59 backticked + 2 bold-prose in `mlflow-evaluation`, **3 in `databricks-app-design`** | 11 is the file count, not occurrences; second skill unlisted; `](` regex finds 0 |
| SPEC-10b labels (D12) | — | 64 excludes link labels; counting labels inflates to **167** | a basename in a link *label* is display text, not a defect; basenames resolving at the skill root are NEW-C, not SPEC-10b; new |
| PD-5 | 17 skills, pipelines 103 | **228** links / **15** skills / 69 files, pipelines **91** | both totals and per-skill differ |
| PD-6 | ~120 / 25 skills | **125** of 137 / **26** skills | heuristic-stable (123–125); 12 files already have TOCs |
| PD-6 root files (D10) | — | 125 = 121 under `references/` + 4 root-level | excluding root-level files is NEW-C's exact blind spot; new |
| PD-1/2/3 | 839/15,683 etc. | **exact match** under D6 | no drift once `round(chars/4)` is used |
| PD-4a | 2 | **3** | third in `experimental/spark-python-data-source:145` |
| PD-4b | 26 `parent: databricks-core` | **25**; 1 `parent: databricks-apps`; 6 unparented; **19** children unmentioned | parent graph incomplete |
| PD-4c | 3 orphans | **3** | exact |
| DESC-1/3 | 5 skills | **6** on review; regex flags 8–10 | `genie-agents` is a 6th; not mechanically decidable |
| TOK-5 | 30 / 10 skills | **21/10** strict; **85–87/15** broad; **27/9** SKILL.md-only broad | audit ≈ SKILL.md-only broad **plus a phantom 3 for `serverless-migration`, which has no preview/beta text at all** |
| Compat pins | 4 values | 4 + **3 absent** + **1 `databricks-air`**; **6** distinct literals incl. bodies | audit undercounted shapes; `jobs` and `python-sdk` contradict their own frontmatter |
| Resident set | 2,975 / 3,199 | **2,975 / 3,199** | exact — but only with YAML `\"` unescaped |
| PD-8 gotchas | 29 skills | **30** | only `ml-training` and `pipelines` have one |
| PD-8 "Troubleshooting" (D13) | — | 30 strict vs **25** admitting `troubleshoot` | 5 more skills credited: core, genie-agents, lakebase, model-serving, unstructured-pdf-generation; new |
| MNT-8 versions | 21 at `0.1.0` | **24** at `0.1.0`; `databricks-dabs` has **no `metadata`** | audit undercounted |
| Dangling links | not measured | **7 total corpus-wide** at baseline (6 NEW-A + 1 NEW-B); **6** now, NEW-B's link became prose in the PD-5 sweep | new |

---

## Deferred to other branches

Nothing goes into a diff its branch does not own.

- **`specs/02` reconciliation landed on `ralph/spec-10a-remainder`, not
  deferred.** The self-parent exemption claimed subset-install breakage was
  "the sole rationale for the SPEC-10a class", which read literally also
  exempts the 19 `SPEC-10a-intra` links — same path, same kind of file, one
  row advisory and one must-fix. The reconciliation names the second,
  independent rationale (a link is a load instruction and `references/` loads
  only after `SKILL.md` has fired, so a link back to it is dead routing that
  cannot be rewritten) and scopes the exemption to non-link mentions. Both
  rows are 0, so nothing turned on it — recorded so a future reader does not
  harmonise the rows and un-gate one.
- **`SPEC-10a` regression guard in `scripts/skillsgen/validators.py` is NOT in
  this branch.** `specs/02`'s SPEC-10a fix text ends "then add a traversal
  check to `validators.py` so it cannot regress", but that is item 16 /
  MNT-1b, a different finding class, and wiring it into `cli.py`'s `validate`
  sequence early makes `validate` exit 1 for every other branch. It also has
  to reimplement both exemptions (81 in-fence, 3 self-parent) or it reports
  84 false positives on a clean corpus. Last sweep PR only.

- **Observed while sweeping SPEC-10b, NOT a defect — do not "fix" it.** 56
  bold skill mentions across the corpus are written `**databricks-x**` where
  the majority house form is ``**`databricks-x`**`` (heaviest:
  `databricks-lakeflow-connect` 11, `databricks-vector-search`,
  `databricks-docs`). No spec rule governs backtick style on a skill name and
  no checker row counts it. Recorded so a future loop recognises it as
  pre-existing rather than damage from the SPEC-10a-cross sweep.

- NEW-C → branch 6 (item 9).
- `databricks-app-design`'s 3 bare basenames → branch 5 (item 5), not a new branch.
- `experimental/databricks-ai-runtime/SKILL.md:33` → branch 6 with the other 11.
- `databricks-jobs` / `databricks-python-sdk` frontmatter-vs-body version
  contradictions → branch 15; they are fixable without the blocked global value.
- ~~**Stale row in the count table above:** `SPEC-10a-prose` reads 3~~ —
  **fixed.** The row now reads 0, matching the checker since `2b9807a` exempted
  self-parent `../SKILL.md` under D8 (the 3 moved to the advisory
  `SPEC-10a-self-parent` row, which the table was also missing).
  `specs/02-audit-findings.md` was corrected in `bc9ddb7`. `SPEC-10a-prose`
  stays a must-fix row at 0 so a regression is caught; branch 4 is a guard, not
  a sweep.
- `experimental/README.md` carries 10 `../` link occurrences (lines 10, 15, 40,
  50, 51, 65–67, 70, 71) but sits OUTSIDE every skill directory, so
  `iter_all_skill_dirs` never scans it and no finding counts it. Confirmed out
  of corpus scope — `specs/01`'s link rules govern skill directories. Not a
  defect; do not "fix" it.
- `skills/databricks-spark-structured-streaming/references/lakebase-sink-python.md:13`
  retains an intra-`references/` link `[real-time-mode.md](real-time-mode.md)`.
  That is PD-5, already inside the 228, and belongs to branch 7.

---

## File as issue, do not PR

Upstream cannot merge PRs directly; these need a decision, not a diff.

- **`[NEW]` Two more pointers to skills that do not exist, in the same list as
  PD-4a's third site.** `experimental/spark-python-data-source/SKILL.md:144`
  names `databricks-testing` and `:146` names `python-dev`; neither exists in
  this repo under any spelling. Found by sweeping every `databricks-*` token in
  the corpus against the real directory set — the other 36 candidate names are
  all false positives (PyPI packages `databricks-sdk` / `databricks-connect` /
  `databricks-vectorsearch`, Foundation Model endpoint names
  `databricks-claude-sonnet-4` / `databricks-gte-large-en`, env vars, and the
  repo's own name). **`PD-4a` does not count these**: the row hardcodes the one
  dead name `databricks-spark-declarative-pipelines`, so the class is real but
  the gate is narrower than the class. *Policy: which skills those two lines
  meant is unknowable from the corpus — the same situation as NEW-B, and
  guessing ships a wrong pointer. Either a maintainer names the targets or the
  two lines are dropped.*

- **`[NEW]` NEW-B — `plugin-contracts.md` does not exist. Still open; the row
  now reads 0.** `skills/databricks-apps/references/appkit-proto-first.md:306`
  (was `appkit/proto-first.md:306`) pointed at `references/plugin-contracts.md`.
  A full-repo search finds **no file of that name anywhere, under any path**.
  The old plan asserted that flattening `appkit/` fixes it — it does not;
  flattening only changes where a broken link points.
  **What actually happened:** PD-5 requires the link gone regardless of its
  target, so `ec4c42e`'s predecessor `6fe7086` gave it the same mechanical strip
  as the other 227 and the line now reads `- plugin-contracts — proto↔plugin
  type mappings…` in prose. That ships no broken pointer and asserts no path,
  but it does drop `NEW-B` to 0 — **the row being zero does not mean the
  question is answered**. `appkit-proto-contracts.md` (202 lines, same dir) is a
  plausible intended target but that is a guess. *Policy unchanged: someone must
  say what the link meant; guessing ships a wrong pointer.*
- **D1 — `../` in code fences vs `specs/01`'s flat ban.** The rule read
  literally would corrupt **81 working examples across 5 skills**
  (`databricks-jobs` alone holds 64 DAB paths). The repo's own
  `databricks-dabs/references/bundle-structure.md` documents `../src/...` as
  *required* for `resources/*.yml`. `specs/01` needs a written code-fence
  exemption. *Policy: amends the structural contract, not a file.*
- **D5 — preview-marker definition.** Strict 21/10, broad 85–87/15,
  SKILL.md-only broad 27/9, audit says 30/10 — and the audit's figure appears to
  include 3 markers attributed to a skill with none. *Policy: no diff is correct
  until the definition is.*
- **DESC when-clause decidability.** Regex flags 8–10, review names 6. *Policy:
  "does this text state a condition" is a judgement call. Propose a reviewed
  allowlist in the checker, or drop the automated gate.*
- **Compatibility pin target value.** Needs a verified current Databricks CLI
  version, plus decisions on the 3 empty `compatibility` fields and whether
  `experimental/databricks-ai-runtime`'s `databricks-air` pin is intentional.
  *Policy: guessing a version ships a wrong requirement to every user.*
- **PD-4b parent assignment** for `databricks-dabs`, `databricks-genie-agents`,
  `databricks-zerobus-ingest`, and the `parent: databricks-apps` outlier.
  *Policy: taxonomy ownership, not a defect.*
- **MNT-1** — `scripts/skills.py validate` runs 19 checks but none touch skill
  content: not `name` charset, name-matches-directory, the 1,024 cap, the
  500-char `compatibility` cap, XML, body size, link form, or traversal
  (verified per-rule). Propose promoting `audit_check.py` into the CI contract.
  *Policy: changes CI contract.*
- **SPEC-9** — `parent:` is documented in `CONTRIBUTING.md` but absent from the
  Agent Skills spec, which designates `metadata` as the extension point.
  Propose `metadata.parent`; accept a documented rejection. *Policy: schema
  change with downstream consumers.*
- **MNT-2** — zero evaluations across 32 skills against a published floor of
  three per skill. *Policy: resourcing commitment.*
- **MNT-8** — `metadata.version` is inert: **24** skills at `0.1.0`,
  `databricks-dabs` has no `metadata` block at all, nothing bumps on content
  change, releases run off `metaplugin/version.meta.json` (`0.2.10`).
  `databricks-app-design`'s value is unquoted — harmless, since YAML's float
  regex rejects two decimal points, so it still parses as `str`. *Policy:
  release-process decision.*
- **DBX-3** — `docs.databricks.com/aws/en/agent-skills/` lists 8 skills; the
  repo ships 30. Same table lists AI Dev Kit as live while
  `experimental/README.md` calls it deprecated. *Docs-side; not fixable here.*
- **MNT-7a** — `experimental/README.md` self-contradicts on re-sync cadence.
- **MNT-7b** — `.gen.json` pins
  `source_commit: 70f06e3196ff3b0a6807a8796f5c8c95efc05ce5`, not an object in
  this repo's history. *Policy: provenance from the internal repo.*
- **TOK-5 / MNT-6 reconciliation** — now recorded in
  `specs/02-audit-findings.md` (a Reconciliation section is being appended
  there in parallel); see that spec for detail, not duplicated here.

## Confirmed NOT defects — do not plan a fix

- **All frontmatter hard limits are already at zero** across 32 skills: `name`
  charset / length / equals-dirname / no `anthropic`|`claude`; `description`
  presence and ≤1,024; `compatibility` ≤500 (max 154); `metadata` string→string;
  XML in any value. Ship as regression guards only.
- **The 81 in-fence `../`** — DAB paths, TS imports, and one deliberate
  "before" example. Zero target a `.md`.
- **8 of the 13 prose `../`** — documentation *about* traversal, not traversal.
- **14 apparent `../`** — `.../` ellipsis false positives.
- **The two-H2 skeleton** — 0/32 comply, and `specs/01` scopes the rule to newly
  authored skills. Gate item 17 only.
- **SPEC-11** — `agents/openai.yaml` and `assets/` sit outside the spec's
  directory set, but `CONTRIBUTING.md` requires both for every skill as Codex
  marketplace metadata. Deliberate.
- An independent second measurement of the `../` corpus (blind to
  `scripts/audit_check.py`) returned 87 in-fence and 8 ellipsis false
  positives vs the checker's 81 and 14. Not a disagreement: the checker
  strips ellipsis matches BEFORE classifying, so the 6 occurrences that are
  both in-fence and ellipsis-abutting land in the ellipsis bucket. Totals
  reconcile. No spec change needed.
