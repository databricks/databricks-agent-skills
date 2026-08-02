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
- Run it from the repo root — it resolves the corpus relative to its own
  path, so any cwd works, but the paths it prints are repo-relative.
- The counting conventions (token basis, the `../` matcher's ellipsis
  exclusion, code-fence exemption, TOC heuristic) live in the module
  docstring — that's the contract; changing one moves every number.
- Tests: `tests/audit_check_test.py`, run via
  `python3 -m unittest discover -s tests -p '*_test.py'`. They pin the
  conventions against fixtures, not the corpus's current counts, so they stay
  green as findings are swept.
- Quote the glob in raw grep cross-checks — an unquoted `--include=*.md`
  aborts under zsh.
