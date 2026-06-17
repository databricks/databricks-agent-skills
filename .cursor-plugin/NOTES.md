# The Cursor plugin `name` is the install identifier

The `name` field in this `plugin.json` is **`databricks`**. It is the
identifier Cursor uses for `/add-plugin databricks` and for tracking installed
copies under `~/.cursor/plugins/databricks/`. The marketplace URL slugs
(`cursor.com/marketplace/databricks`, `cursor.com/marketplace/databricks-apps`)
are display-only and do not drive the install command.

It matches the Claude Code plugin
([`../.claude-plugin/plugin.json`](../.claude-plugin/plugin.json)) so both
agents install under the single brand word `databricks`, following the
github/gitlab/terraform/linear convention.

## Don't change `name` casually

Cursor keys installs and auto-updates on this identifier. The plugin shipped as
`databricks-skills` from its first publish (2026-02) until it was renamed to
`databricks` alongside a coordinated Cursor-side migration, so existing installs
kept receiving updates. Any future change carries the same risk and needs the
same coordination; otherwise it orphans every existing install until users
reinstall. `scripts/skills.py` enforces the current value.
