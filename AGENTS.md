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
