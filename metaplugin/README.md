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

- **Plugin manifests**: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
  `.github/plugin/plugin.json`, `.cursor-plugin/plugin.json`
- **Marketplace catalogs**: `.claude-plugin/marketplace.json`,
  `.github/plugin/marketplace.json`, `.agents/plugins/marketplace.json`
- **Hook wiring**: `hooks/hooks.json`, `hooks/codex-hooks.json`,
  `hooks/copilot-hooks.json`, `hooks/cursor-hooks.json`
- **Prompt routing**: `hooks/_routing_data.json` and `rules/databricks-routing.mdc`
  (both rendered from the one `routing` table, so they cannot drift)
- **Skill manifest**: `manifest.json`
- The `README.md` marker in each generated directory above

## NOT generated — edited in place

This folder holds the cross-target *metadata*, not every editable file. The
following are hand-edited where they live, because each is loaded from a fixed
runtime path:

- **Hook scripts**: `hooks/*.py` (`databricks-router.py`, `databricks-context.py`,
  `databricks-auth-helper.py`). One shared copy per script; editing it already
  propagates to every target. `plugin.meta.json` only wires *which* script runs
  on *which* event, in each runtime's dialect (the `hooks` block + each target's
  `hooks_render`).
- **Slash commands**: `commands/*.md` (Claude / Codex), `commands-cursor/*.md` (Cursor)
- **Skills**: `skills/**` and `experimental/**`

See [CONTRIBUTING.md](../CONTRIBUTING.md) ("Plugin metadata") for the full field
reference, and [scripts/skillsgen/](../scripts/skillsgen/) for the generator.
