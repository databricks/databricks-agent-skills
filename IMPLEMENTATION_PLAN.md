# Implementation plan

Corpus: 32 skill dirs (30 `skills/`, 2 `experimental/`), 204 `.md` files, 311
files total. Measured at HEAD `50ccd08` + working tree.

**Two of three goals are already green.** `python3 scripts/skills.py validate`
exits 0; `python3 -m unittest discover -s tests -p '*_test.py'` runs 118 tests,
all pass. The job is to keep both green while driving `scripts/audit_check.py`
— **which does not exist** (verified: `scripts/` holds only `bump_version.py`,
`skills.py`, `skillsgen/`) — to zero must-fix.

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

## 1. MNT-1a — author `scripts/audit_check.py` — BLOCKS EVERYTHING

- **Finding:** MNT-1a
- **Path:** `scripts/audit_check.py` (new); tests in `tests/audit_check_test.py` (new)
- **Count:** 0 checkers → **target 1 gate covering all 32 skills**
- **Backpressure:** `python3 scripts/audit_check.py` runs and its per-class
  totals equal **this plan's** numbers (not `specs/02`'s, wherever they
  differ); then `python3 scripts/skills.py validate; echo $?` → `0` and
  `python3 -m unittest discover -s tests -p '*_test.py'` → 118 pass.

Implements the D-definitions above plus, per `specs/01`: frontmatter limits;
body `< 500` lines and `< 5,000` tokens; traversal classes; reference-to-
reference; orphans; link form; TOC over 100 lines; description when-clause.
Emit a per-skill table plus a rollup keyed by finding ID. Support
`--only <ID>` so every item below has a one-command gate — note there is **no
existing optional-flag precedent** in this repo's scripts, so `--only` is new
surface; match `cli.py`'s argparse style.

**Six rules are already at zero** and ship as regression guards, not fixes:
`name` charset / ≤64 / equals dirname / no `anthropic`|`claude` (0 violations);
`description` 1–1024 (0; range 122–845); no XML in any frontmatter value (0 —
the only `<` in any frontmatter is `<10K rows` in
`databricks-synthetic-data-gen`); `compatibility` ≤500 (0; max 154);
`metadata` string→string (0).

**Do NOT** wire anything into `scripts/skillsgen/validators.py` yet. The house
test pattern is `self.assertEqual(skills.check_x(_REPO), [])` — 9 such
assertions exist. Adding one before its class is at zero turns 118 green tests
red. Tracked as item 16.

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

**Lands last of the link/structure sweeps.** **56 of the 125 files are also
PD-5 sources** — building TOCs first means regenerating every one of those 56.
Split into ≥3 commits by skill so a 125-file diff stays cherry-pickable.

---

## 3. PD-5 — reference-to-reference links — 228 → 0

- **Finding:** PD-5
- **Paths:** 228 links, 69 source files, **15 skills**.
  `skills/databricks-pipelines` **91** (own commit),
  `skills/databricks-unity-catalog` 29, `skills/databricks-aibi-dashboards` 19,
  `skills/databricks-apps` 19,
  `skills/databricks-spark-structured-streaming` 15,
  `skills/databricks-metric-views` 13, `skills/databricks-lakebase` 9,
  `skills/databricks-ml-training` 8, `skills/databricks-execution-compute` 6,
  `skills/databricks-iceberg` 6, `skills/databricks-apps-python` 5,
  `skills/databricks-lakeflow-connect` 2,
  `skills/databricks-serverless-migration` 2,
  `skills/databricks-zerobus-ingest` 2,
  `experimental/spark-python-data-source` 2
- **Count:** 228 → **0**
- **Backpressure:** `python3 scripts/audit_check.py --only PD-5` → 0

Strip inter-reference links to plain names; ensure every reference is linked
directly from its `SKILL.md` with a stated load condition. A second hop is
invisible to a partial read (`head -100`).

**Depends on item 4** — but only narrowly: cross-skill and PD-5 share just
**6 files** (`aibi-dashboards/references/2-advanced-widget-specifications.md`,
`lakebase/references/{off-platform,pgvector}.md`,
`pipelines/references/real-time-mode.md`,
`spark-structured-streaming/references/{lakebase-sink-python,real-time-mode}.md`).
The old plan's claim that unity-catalog is a conflict site is wrong — it shares
zero files with the traversal classes.

### 3a. PD-5b — flatten `references/appkit/` — 12 files → 0 nested

- **Finding:** PD-5b
- **Path:** `skills/databricks-apps/references/appkit/*.md` →
  `skills/databricks-apps/references/appkit-*.md`; update every inbound link in
  `skills/databricks-apps/SKILL.md`
- **Count:** 12 files in the repo's **only** two-level reference dir → 0 nested
- **Backpressure:** `test ! -d skills/databricks-apps/references/appkit` and
  `python3 scripts/audit_check.py --only PD-5b` → 0

Inventory (lines): `lakebase.md` 439, `files.md` 324, `proto-first.md` 307,
`genie.md` 304, `sql-queries.md` 268, `model-serving.md` 223,
`proto-contracts.md` 202, `frontend.md` 175, `custom-endpoints.md` 162,
`overview.md` 150, `jobs.md` 142, `appkit-sdk.md` 107.

---

## 4. SPEC-10a-cross — cross-skill `../` traversal — 90 → 0

- **Finding:** SPEC-10a-cross (includes **NEW-A**)
- **Paths:** 90 links, 26 files, **20 skills**.
  `skills/databricks-ml-training` 14, `skills/databricks-unity-catalog` 11,
  `skills/databricks-apps-python` 8, `skills/databricks-pipelines` 7,
  `skills/databricks-spark-structured-streaming` 7,
  `skills/databricks-aibi-dashboards` 6, `skills/databricks-genie-agents` 4,
  `skills/databricks-mlflow-evaluation` 4, then 12 skills with 1–3
- **Count:** 90 → **0**
- **Backpressure:** `python3 scripts/audit_check.py --only SPEC-10a-cross` → 0

Replace each cross-skill file path with the bare skill name in prose. There is
no valid cross-skill link form — do not invent one. Skills install as subsets;
the path dangles by construction.

**Raw floor is a smoke check only, never the gate:**
`grep -rn '](\.\./databricks-' skills/ experimental/ --include='*.md' | wc -l`
→ 68 lines (71 occurrences). It misses the **19** deeper forms whose target
does not start `../databricks-`: 15 × `../../`, 2 × `../../skills/`, 2 ×
`../../../`. Those live in `agent-bricks`, `aibi-dashboards` ×2,
`apps/references/appkit/lakebase.md` ×2, `execution-compute`, `lakebase` ×3,
`ml-training` ×2, `pipelines/references/real-time-mode.md` ×7,
`spark-structured-streaming` ×1. (Quote the glob — unquoted `--include=*.md`
aborts under zsh. Same for every raw command in this plan.)

### 4a. `[SEV]` NEW-A — 6 traversals that are also **dangling** — fix here

- **Finding:** NEW-A (not in `specs/02`)
- **Path:** `skills/databricks-spark-structured-streaming/references/lakebase-sink-python.md`
  lines **13 (×2), 20, 117, 277, 312**
- **Count:** 6 → **0**
- **Backpressure:** `grep -c '\.\./databricks-lakebase'
  skills/databricks-spark-structured-streaming/references/lakebase-sink-python.md`
  → 0 (currently 6 occurrences)

Targets `../databricks-lakebase/references/{connectivity,computes-and-scaling,lakehouse-sync}.md`.
All three files exist under `skills/databricks-lakebase/references/`, but from
inside `references/` a single `../` resolves to the streaming skill's own root —
it would need `../../`. **These are broken today, even in a full checkout.**
A full-corpus link resolution found exactly **7 dangling relative `.md` links**
in the entire repo: these 6 plus NEW-B. The prose fix (name
`databricks-lakebase`, drop the path) closes both defects at once.

---

## 5. SPEC-10b — bare-basename references — 64 → 0

- **Finding:** SPEC-10b
- **Paths:** `skills/databricks-mlflow-evaluation/SKILL.md` (61 mentions of all
  11 of its `references/` files) and **`skills/databricks-app-design/SKILL.md`
  lines 27, 29, 30** (3 mentions: `dashboard-patterns.md`, `ibcs-notation.md`,
  `appkit-cheatsheet.md`)
- **Count:** **64 → 0** — 59 backticked + 2 bold-prose in mlflow-evaluation,
  3 backticked in app-design
- **Backpressure:**

  ```sh
  grep -oE '`[A-Za-z0-9._-]+\.md`' skills/databricks-mlflow-evaluation/SKILL.md \
    | grep -vc 'references/'                                    # 59 -> 0
  grep -cE '\*\*Read [A-Za-z0-9._-]+\.md\*\*' \
    skills/databricks-mlflow-evaluation/SKILL.md                # 2  -> 0
  grep -oE '`[A-Za-z0-9._-]+\.md`' skills/databricks-app-design/SKILL.md \
    | grep -vc 'references/'                                    # 3  -> 0
  ```

  Canonical: `python3 scripts/audit_check.py --only SPEC-10b`.

**Both `specs/02` and the previous plan are wrong on scale and scope.** The
count of 11 is the number of *files*, not occurrences — there are **61**
mentions in mlflow-evaluation alone, and the class extends to a **second
skill** neither document names. Zero of the 64 are markdown links.

**Byte-preserve the rest of `mlflow-evaluation/SKILL.md`** — its numbered
workflow tables (52 of the 61 mentions sit in table cells) are the best routing
in the repo; only the paths are wrong. Decide once and apply uniformly: keep as
backticked text with the prefix, or promote to markdown links.

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

## 7. SPEC-10a-intra — `../` inside a skill — 21 → 0

- **Finding:** SPEC-10a-intra
- **Paths:** 21 links, 19 files, **9 skills**. `skills/databricks-pipelines` 5,
  `skills/databricks-ml-training` 4, `skills/databricks-agent-bricks` 3,
  `skills/databricks-ai-functions` 3, `skills/databricks-apps` 2, and 1 each in
  `aibi-dashboards`, `lakeflow-connect`, `metric-views`,
  `serverless-migration`
- **Count:** 21 → **0**. Zero are dangling.
- **Backpressure:** `python3 scripts/audit_check.py --only SPEC-10a-intra` → 0

19 of the 21 are `../SKILL.md` (often with an anchor) from a `references/`
file; 2 are `references/appkit/{jobs,model-serving}.md → ../platform-guide.md`,
which **item 3a's flatten resolves** — sequence after PD-5b or expect a
conflict. Safer fix than item 4: rewrite relative to the skill root; the target
never leaves the install subset.

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

## 9. `[SEV]` NEW-C — reference files at the skill root — 4 files / 12 links → 0

- **Finding:** NEW-C (not in `specs/02`)
- **Paths:** `skills/databricks-core/{databricks-cli-auth,databricks-cli-install,manual-data-exploration}.md`
  and `experimental/databricks-ai-runtime/docker-images.md`
- **Count:** 4 files, **12** bare-basename links → 0.
  `skills/databricks-core/SKILL.md` lines 26, 32, 37, 87, 141, 149, 150, 151,
  156, 157, 158 (**11**) plus
  `experimental/databricks-ai-runtime/SKILL.md:33` (**1** — missed by the
  previous plan, which said 11).
- **Backpressure:** `ls skills/databricks-core/*.md experimental/databricks-ai-runtime/*.md
  | grep -vc SKILL.md` → 0; then `python3 scripts/skills.py generate` and
  `python3 scripts/skills.py validate; echo $?` → 0 with a clean `git status`

They resolve on disk, so nothing is user-visibly broken — but they violate
`specs/01`'s link rule ("a bare basename is a defect even when the file
resolves by luck") **and** every `references/`-scoped check skips them
silently: no TOC check, no orphan check, no one-level-deep check. Three of the
four sit in the repo's entry-point skill.

**`scripts/skills.py generate` IS required — now verified, not assumed.**
`manifest.json` enumerates per-file paths per skill via `iter_skill_files()` /
`rglob` (`scripts/skillsgen/manifest.py`), listing these four basenames
directly; `plugins/databricks/{claude,codex,copilot,cursor}/skills/...` is a
recursive byte-for-byte mirror (`scripts/skillsgen/bundle.py`). Both go stale
on the move and `validate` **does** catch it (manifest content mismatch +
missing/orphan bundle files). The four `marketplace.json` catalogs and
`agents/openai.yaml` reference skill **directories** only and are unaffected.
The 12 markdown links are a manual fix — no generator or validator parses
SKILL.md link targets.

---

## 10. Compatibility pin — 4 pins + 3 absent + 1 other-CLI → 1 — BLOCKED

- **Finding:** Compatibility pin inconsistency
- **Paths:** frontmatter across 28 skills, plus **7 skills hardcoding a CLI
  version in the body**: `skills/databricks-core/SKILL.md:31`,
  `skills/databricks-agent-bricks/SKILL.md:60`,
  `skills/databricks-data-discovery/SKILL.md:61,78,121`,
  `skills/databricks-jobs/SKILL.md:44`,
  `skills/databricks-lakebase/SKILL.md:346`,
  `skills/databricks-lakeflow-connect/SKILL.md:96`,
  `skills/databricks-python-sdk/SKILL.md:89`,
  `skills/databricks-unity-catalog/SKILL.md:17`
- **Count:** `>= v1.0.0` (20), `>= v0.294.0` (5), `>= v0.292.0` (2),
  `>= v1.9.0` (1); **3 with no `compatibility`** (`databricks-app-design`,
  `databricks-dabs`, `databricks-vector-search`); **1 pinning a different CLI**
  (`experimental/databricks-ai-runtime` → `databricks-air`, legitimately
  different). **6 distinct CLI version literals** once bodies are counted →
  target 1, or per-skill values individually justified
- **Backpressure:** `grep -h '^compatibility:' skills/*/SKILL.md
  experimental/*/SKILL.md | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | sort -u | wc -l`
  → 1, and `python3 scripts/skills.py validate; echo $?` → 0

**BLOCKED on a verified current Databricks CLI version. Do not guess a value.**
Plan it, then stop. Derive from one constant in `scripts/skillsgen/`.

**Two skills contradict themselves** (new, beyond `specs/02`):
`databricks-jobs` pins `>= v1.0.0` in frontmatter but says `>= v0.288.0` at
line 44; `databricks-python-sdk` pins `>= v1.0.0` but says `>= 0.278.0` at line
89. Those two are internally inconsistent regardless of which global value wins,
and can be fixed independently of the blocked decision.

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

## 12. DESC-1 / DESC-3 — descriptions without trigger conditions — 6 → 0

- **Finding:** DESC-1 / DESC-3
- **Paths / counts (chars), rewrite shortest first:**
  `skills/databricks-agent-bricks` (122, shortest in repo),
  `skills/databricks-vector-search` (133, "covers index types, search modes" —
  contents, not conditions), `skills/databricks-execution-compute` (173),
  `skills/databricks-unstructured-pdf-generation` (253),
  **`skills/databricks-genie-agents` (350 — 6th, not in `specs/02`)**,
  `skills/databricks-ai-functions` (415)
- **Count:** **6 → 0**
- **Backpressure:** `python3 scripts/audit_check.py --only DESC-1` → 0, and the
  rollup's resident-set line printed for the PR body

**Use a fixed reviewed list, not a regex gate.** `specs/02` names 5; a
when-clause regex flags 8–10 depending on wording, and independent review says
**6**. `databricks-genie-agents` opens with a bare capability list ("Create,
manage, and query…") and carries only a *negative* sibling clause, never a
positive self-trigger — structurally identical to `agent-bricks`. The extra
regex hits (`unity-catalog`, `core`, `ml-training`) are false positives:
"Use to grant or revoke…" and "Load this first for…" are valid elided-object
self-references. Hardcode the reviewed 6; file the heuristic as an issue.

Target 300–500 chars, hard cap 1,024 (currently 0 violations; max 845).
Model: `skills/databricks-data-discovery` (literal user phrasings); second-best
`skills/databricks-apps-python` (names its sibling and when it wins instead).
Baseline resident set **2,975 tokens stable / 3,199 all-in** — reproduced
exactly, but only after unescaping YAML `\"` in the `apps` and `unity-catalog`
descriptions; a naive parser reports 2,964/3,187.

---

## 13. PD-4a — dead skill pointer — 3 → 0

- **Finding:** PD-4a
- **Paths:** `skills/databricks-docs/SKILL.md:23`,
  `skills/databricks-docs/SKILL.md:52`,
  `experimental/spark-python-data-source/SKILL.md:145`
- **Count:** **3 → 0** (`specs/02` says two places; the third is in
  `experimental/`, which the audit did not scan for this finding)
- **Backpressure:** `grep -ro 'databricks-spark-declarative-pipelines' skills/
  experimental/ | wc -l` → 0 (currently 3)

All three name a non-existent `databricks-spark-declarative-pipelines`; the real
skill is `databricks-pipelines`. While in `databricks-docs/SKILL.md`, settle
terminology — it mixes "Delta Live Tables", "DLT", and "Lakeflow" for one
product in a 60-line body. **Separate commit** from the pointer fix.

---

## 14. PD-4c — orphan reference files — 3 → 0

- **Finding:** PD-4c — exact match with `specs/02`, independently confirmed
  against all 172 reference files
- **Paths:** `skills/databricks-lakebase/references/medallion-from-cdc.md`,
  `skills/databricks-pipelines/references/python-basics.md`,
  `skills/databricks-pipelines/references/sql-basics.md`
- **Count:** 3 → **0**
- **Backpressure:** `python3 scripts/audit_check.py --only PD-4c` → 0

None is a true dead end — each is reachable one hop away from a reference file
that *is* linked from `SKILL.md` (`lakehouse-sync.md`/`synced-tables.md`;
`dlt-migration.md`/`2-rapid-iteration-with-cli.md`). That is exactly the PD-5
second-hop failure mode, so **fixing PD-5 will orphan them harder** — sequence
after item 3. Link from the owning `SKILL.md` with a load condition, **or**
delete; say which and why in the commit message.

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
traversal (`../`)"), `databricks-apps/references/appkit/files.md:323` (an error
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
  `specs/02` says 29). MNT-6 — `skills/databricks-synthetic-data-gen/scripts/generate_synthetic_data.py`
  and `skills/databricks-unstructured-pdf-generation/scripts/pdf_generator.py`;
  confirmed these are the only two skills bundling `scripts/`, and neither
  SKILL.md states run-vs-read intent
- **Count:** 30 → 0; 2 → 0
- **Backpressure:** not a must-fix gate — do not let it block the definition of
  done. `python3 scripts/audit_check.py --only PD-8,MNT-6` reported as advisory.

---

## Landing order (dependency-forced — differs from priority order)

Priority ranks by blast radius; execution must respect file overlap. Measured
overlap: PD-5 ∩ PD-6 = **56 files**; cross ∩ PD-5 = 6; intra ∩ PD-5 = 8;
intra ∩ PD-6 = 13; cross ∩ intra = 3.

| Step | Branch | Item | Count → target |
|---|---|---|---|
| 1 | `ralph/audit-check-bootstrap` | 1 · MNT-1a | 0 → 1 gate |
| 2 | `ralph/spec-10a-cross` | 4 · SPEC-10a-cross + NEW-A | 90 → 0 |
| 3 | `ralph/spec-10a-intra` | 7 · SPEC-10a-intra | 21 → 0 |
| 4 | `ralph/spec-10a-prose` | 15 · SPEC-10a-prose | 3 → 0 |
| 5 | `ralph/spec-10b-basenames` | 5 · SPEC-10b | 64 → 0 |
| 6 | `ralph/new-c-root-refs` | 9 · NEW-C (+ `generate`) | 12 links / 4 files → 0 |
| 7 | `ralph/pd-5-flatten` | 3 + 3a · PD-5, PD-5b | 228 → 0; 12 → 0 |
| 8 | `ralph/pd-4c-orphans` | 14 · PD-4c | 3 → 0 |
| 9 | `ralph/pd-6-toc` | 2 · PD-6 (≥3 commits) | 125 → 0 |
| 10 | `ralph/pd-1-ceilings` | 11 · PD-1/2/3 (1 commit each) | 4 → 0 |
| 11 | `ralph/pd-4a-dead-pointer` | 13 · PD-4a | 3 → 0 |
| 12 | `ralph/desc-1-triggers` | 12 · DESC-1/3 | 6 → 0 |
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
3. `python3 -m unittest discover -s tests -p '*_test.py'` → 118 pass
4. `git status` clean under `plugins/`, `manifest.json`, `*/marketplace.json`
   (generated — regenerate with `scripts/skills.py generate`, never hand-edit)
5. Single concern; commit message names the finding ID and the before→after count

---

## Measurement disagreements with `specs/02` (record, do not silently adopt)

| Finding | `specs/02` claims | Measured | Nature |
|---|---|---|---|
| SPEC-10a | 19 skills, 128 occ | cross **90**/20 · intra **21**/9 · prose **13**/6 (only **3** are defects) · fence **81**/5 (**0** defects) | audit conflated 4 classes and counted links only; missed `databricks-jobs` (64 in-fence, largest holder, unlisted) |
| SPEC-10a ellipsis | — | naive `\.\./` = 240 vs **226** real | **14 false positives** from `.../` truncation markers; new |
| SPEC-10b | 11 | **64 mentions across 2 skills** — 59 backticked + 2 bold-prose in `mlflow-evaluation`, **3 in `databricks-app-design`** | 11 is the file count, not occurrences; second skill unlisted; `](` regex finds 0 |
| PD-5 | 17 skills, pipelines 103 | **228** links / **15** skills / 69 files, pipelines **91** | both totals and per-skill differ |
| PD-6 | ~120 / 25 skills | **125** of 137 / **26** skills | heuristic-stable (123–125); 12 files already have TOCs |
| PD-1/2/3 | 839/15,683 etc. | **exact match** under D6 | no drift once `round(chars/4)` is used |
| PD-4a | 2 | **3** | third in `experimental/spark-python-data-source:145` |
| PD-4b | 26 `parent: databricks-core` | **25**; 1 `parent: databricks-apps`; 6 unparented; **19** children unmentioned | parent graph incomplete |
| PD-4c | 3 orphans | **3** | exact |
| DESC-1/3 | 5 skills | **6** on review; regex flags 8–10 | `genie-agents` is a 6th; not mechanically decidable |
| TOK-5 | 30 / 10 skills | **21/10** strict; **85–87/15** broad; **27/9** SKILL.md-only broad | audit ≈ SKILL.md-only broad **plus a phantom 3 for `serverless-migration`, which has no preview/beta text at all** |
| Compat pins | 4 values | 4 + **3 absent** + **1 `databricks-air`**; **6** distinct literals incl. bodies | audit undercounted shapes; `jobs` and `python-sdk` contradict their own frontmatter |
| Resident set | 2,975 / 3,199 | **2,975 / 3,199** | exact — but only with YAML `\"` unescaped |
| PD-8 gotchas | 29 skills | **30** | only `ml-training` and `pipelines` have one |
| MNT-8 versions | 21 at `0.1.0` | **24** at `0.1.0`; `databricks-dabs` has **no `metadata`** | audit undercounted |
| Dangling links | not measured | **7 total corpus-wide** (6 NEW-A + 1 NEW-B) | new |

---

## Deferred to other branches

Nothing goes into a diff its branch does not own.

- NEW-A → branch 2 (item 4a). NEW-C → branch 6 (item 9).
- `databricks-app-design`'s 3 bare basenames → branch 5 (item 5), not a new branch.
- `experimental/databricks-ai-runtime/SKILL.md:33` → branch 6 with the other 11.
- `databricks-jobs` / `databricks-python-sdk` frontmatter-vs-body version
  contradictions → branch 15; they are fixable without the blocked global value.

---

## File as issue, do not PR

Upstream cannot merge PRs directly; these need a decision, not a diff.

- **`[NEW]` NEW-B — `plugin-contracts.md` does not exist.**
  `skills/databricks-apps/references/appkit/proto-first.md:306` links
  `references/plugin-contracts.md`. A full-repo search finds **no file of that
  name anywhere, under any path**. The previous plan asserted that flattening
  `appkit/` fixes it — **it does not**; flattening only changes where the broken
  link points. `proto-contracts.md` (202 lines, same dir) is a plausible intended
  target but that is a guess. *Policy: someone must say what the link meant;
  guessing ships a wrong pointer.*
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
