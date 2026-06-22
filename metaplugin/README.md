<!-- Source of truth for the Databricks plugin. Edit here; the rest is generated. -->

# `metaplugin/` — the plugin source

`plugin.meta.json` in this folder is the **single source of truth** for the
Databricks plugin across all four targets (Claude Code, Codex, GitHub Copilot,
Cursor). This is the one place to edit cross-target plugin metadata. After
editing, run:

```bash
python3 scripts/skills.py generate   # re-render everything listed below
python3 scripts/skills.py validate   # what CI runs; fails on any byte drift
```

## Generated from this file (do NOT hand-edit)

CI re-renders all of these in memory and fails on any drift, so edits to them
are reverted:

- **The per-provider bundles**: `plugins/databricks/{claude,codex,copilot,cursor}/`.
  Each is self-contained — its `plugin.json`, a copy of `skills/`, the hook wiring
  + scripts it uses, and (only where applicable) `commands/`, `rules/`, `assets/`.
  Every agent fetches its own provider subfolder (scoped).
- **Marketplace catalogs** (at the repo root): `.claude-plugin/marketplace.json`,
  `.github/plugin/marketplace.json`, `.agents/plugins/marketplace.json`,
  `.cursor-plugin/marketplace.json` (Cursor's is new). Each points a scoped source
  at *its own* provider subfolder, e.g. `plugins/databricks/claude` (currently
  `ref: main`; a mechanical follow-up flips it to tag-pinning), configured under
  `plugin.meta.json` `marketplace.source`.
- **Hook wiring**: `hooks/hooks.json`, `hooks/codex-hooks.json`,
  `hooks/copilot-hooks.json`, `hooks/cursor-hooks.json` (per-dialect, at the root
  so generation doesn't collide). The bundle renames each into the path its
  provider auto-discovers: `hooks/hooks.json` for Claude, Codex, and Cursor;
  root `hooks.json` for Copilot.
- **Prompt routing**: `hooks/_routing_data.json` and `rules/databricks-routing.mdc`
  (both rendered from the one `routing` table, so they cannot drift)
- **Rendered commands**: each provider's command files, rendered from the
  templated `commands/*.md` source into its bundle folder
- **Skill manifest**: `manifest.json` (stable skills' `repo_dir` stays `skills`;
  the CLI files-channel fetches the root `skills/`)
- The `README.md` marker in each generated manifest directory

## NOT generated — edited in place

This folder holds the cross-target *metadata*, not every editable file. The
following are hand-edited where they live, because each is loaded from a fixed
runtime path:

- **Hook scripts**: `hooks/*.py` (`databricks-router.py`, `databricks-context.py`,
  `databricks-auth-helper.py`). One shared copy per script; editing it already
  propagates to every target. `plugin.meta.json` only wires *which* script runs
  on *which* event, in each runtime's dialect (the `hooks` block + each target's
  `hooks_render`).
- **Slash-command templates**: `commands/*.md` — one templated source per command
  (`{{ claude-or-codex | cursor }}` alternation); the per-provider rendered files
  are generated into each bundle folder.
- **Skills**: `skills/**` and `experimental/**`

See [CONTRIBUTING.md](../CONTRIBUTING.md) ("Plugin metadata") for the full field
reference, and [scripts/skillsgen/](../scripts/skillsgen/) for the generator.
