# Agent contributor guide

This repo's contributor and agent instructions live in two files; read them
first:

- **[CLAUDE.md](./CLAUDE.md)** — repo map, skill hierarchy, the generated plugin
  manifests, and the hooks/commands components.
- **[CONTRIBUTING.md](./CONTRIBUTING.md)** — how to add/update a skill, the
  plugin-metadata source of truth, releasing, and the DCO sign-off rule.

## Orientation for changes to the plugin itself

- **Edit the source, not the output.** `metaplugin/plugin.meta.json` is the
  single source of truth for the plugin across all four targets (Claude Code,
  Codex, GitHub Copilot, Cursor). See
  [`metaplugin/README.md`](./metaplugin/README.md) for the full list of what is
  generated from it and what stays hand-edited.
- **The generator** lives in [`scripts/skillsgen/`](./scripts/skillsgen/) (a
  package split by concern); `scripts/skills.py` is a thin façade and the CLI
  entry point. After editing the source, run `python3 scripts/skills.py generate`,
  then `python3 scripts/skills.py validate` (this is what CI runs).
- **Hooks**: the `*.py` hook scripts in [`hooks/`](./hooks/) are hand-written and
  shared across all targets; only the per-target wiring JSON is generated. To
  change or add a hook, see [`hooks/README.md`](./hooks/README.md) ("Changing or
  adding a hook").
- **Never hand-edit generated files** (the per-target `plugin.json` /
  `marketplace.json`, the `hooks/*-hooks.json` wiring, `hooks/_routing_data.json`,
  `rules/databricks-routing.mdc`, `manifest.json`, and the entire
  `plugins/databricks/` bundle — a generated copy of the source). CI re-renders
  them and fails on any drift, including a bundle that does not match a fresh
  build. Edit the source and run `scripts/skills.py generate`.
- **`manifest.json` is generated alongside `plugins/` and has to be staged with
  it.** `generate` writes it, but only `git add` puts it in the commit, and CI
  validates the commit — so a green `validate` in the working tree is not a
  green commit. `git add -A` after every `generate`.

## Auditing skill content

`scripts/skills.py validate` checks the plugin plumbing only — nothing in it
looks at skill content. `python3 scripts/audit_check.py` is the content-side
gate.

- `python3 scripts/audit_check.py` — every finding, rollup table with a count
  per finding ID. Exits 1 while any must-fix finding is above zero.
- `python3 scripts/audit_check.py --only <ID>[,<ID>...]` — the per-finding
  backpressure gate; exits 0 when the selected findings are at zero. Add
  `--details` to list every violation plus a per-skill breakdown. An unknown
  ID exits 2 and prints the known IDs.
- Advisory, blocked, and rollup findings do not affect the exit status unless
  named explicitly in `--only`.
- `--only GEN-1` is the one row that is not skill content: generated artifacts
  against a fresh `skills.py generate`. It measures staleness, not edits, so it
  agrees with `skills.py validate` — regenerate and stage in the same commit as
  the sweep, and both stay green.
- **Substituting a plain name for a link is not mechanical.** Check whether the
  label named the *file* or named a *thing*: the second demotes a product name
  to a filename. Ten across four sites in the PD-5 sweep, every one caught by
  reading the diff — no gate counts them. Fix shape: keep the name,
  parenthesise the pointer.
- Run it from the repo root — it resolves the corpus relative to its own
  path, so any cwd works, but the paths it prints are repo-relative. There is
  no `--root` flag: to measure another commit, `git worktree add` it and run
  *that tree's* copy of the script.
- Editing skill markdown makes `scripts/skills.py validate` fail until you run
  `python3 scripts/skills.py generate` — `plugins/<target>/skills/**` is a
  byte-for-byte mirror of the source files, so a content sweep dirties 4
  bundle copies per file. `manifest.json` only changes when a file is added,
  removed, or renamed.

- **A sweep that creates, moves, or lengthens a reference file regresses other
  rows.** `--only <ID>` cannot see it; always finish with the unscoped run.
  Observed: moving content into `references/` turns its `references/x.md` links
  into second hops (**PD-5** *and* **NEW-A**, same links counted twice) and
  orphans whatever that content was routing (**PD-4c**); adding a TOC whose
  label repeats a heading's `(Beta)` / `(Public Preview)` raises blocked
  **TOK-5**. Fix these in the commit that caused them.
- **The TOC heuristic is a placement rule, not just a detector.** `## Contents`
  must fall in the first 60 lines. Inserting it before the first section
  heading puts it outside that window when a file opens with a long code block
  — the file then still counts as TOC-less and takes a second TOC on the next
  pass.
- The counting conventions (token basis, the `../` matcher's ellipsis
  exclusion, code-fence exemption, TOC heuristic) live in the module
  docstring — that's the contract; changing one moves every number.
- Tests: `tests/audit_check_test.py`, run via
  `python3 -m unittest discover -s tests -p '*_test.py'`. They pin the
  conventions against fixtures, not the corpus's current counts, so they stay
  green as findings are swept.
- Quote the glob in raw grep cross-checks — an unquoted `--include=*.md`
  aborts under zsh.
