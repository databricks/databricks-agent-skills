# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, etc.) that provide Databricks-specific guidance.

## Structure

```
skills/
├── databricks-core/      # core skill: CLI, auth, data exploration
│   ├── SKILL.md
│   └── *.md (references)
└── databricks-apps/      # product skill: app development
    ├── SKILL.md
    └── references/
```

Hierarchy: `databricks-core` (core) → `databricks-apps` (product) → `databricks-apps-*` (niche)

## Development

### Adding Skills

Create subskills that reference parent:

```markdown
---
name: "databricks-apps-chatbots"
parent: databricks-apps
---

# Chatbot Apps

**FIRST**: Use the parent `databricks-apps` skill for app development basics.

Then apply these patterns:
- Pattern 1
- Pattern 2
```

See [CONTRIBUTING.md](./CONTRIBUTING.md#skill-anatomy) for the full per-skill file layout, including the auto-generated Codex metadata (`agents/openai.yaml`) and shared icons (`assets/databricks.{svg,png}`) that every skill ships.

### Skills management

```bash
python3 scripts/skills.py              # sync metadata/icons, then generate manifest.json + all plugin manifests (default)
python3 scripts/skills.py sync         # sync Codex metadata + icons only
python3 scripts/skills.py validate     # check metadata + icons + manifest + plugin manifests are up to date (CI)
```

## Plugin manifests (generated from `plugin.meta.json`)

The four `plugin.json` files (`.claude-plugin/`, `.codex-plugin/`,
`.github/plugin/`, `.cursor-plugin/`) and the three `marketplace.json` files
(`.claude-plugin/`, `.github/plugin/`, `.agents/plugins/`) are **generated**
from [`plugin.meta.json`](./plugin.meta.json) by `scripts/skills.py generate`.
**Do not hand-edit them** (each generated directory carries a `README.md`
marker). To change the plugin version, description, keywords, or per-target
config, edit `plugin.meta.json` and run `python3 scripts/skills.py generate`; CI
(`validate`) fails on any drift. The version lives only in `plugin.meta.json`
and propagates to all four targets. Adding a stable skill requires an entry in
the `skills` map (with a `keyword`).

The `routing` block in `plugin.meta.json` is generated too: it renders the
prompt router's data (`hooks/_routing_data.json`, loaded by
`hooks/databricks-router.py`) and the Cursor rule
(`rules/databricks-routing.mdc`) from one table. Do not hand-edit those; edit
`plugin.meta.json` and regenerate. CI fails if a product skill has no routing row.

## Plugin components (hooks + commands)

Beyond skills, the Claude Code plugin ships two component dirs at the repo root.
`commands/` is declared via `"commands"` in `.claude-plugin/plugin.json`, but
**`hooks/hooks.json` is auto-loaded by Claude Code and must NOT be declared**
there. Declaring the standard path double-loads it and fails the plugin with a
"Duplicate hooks file" error.

- `hooks/`: a UserPromptSubmit prompt router (`databricks-router.py`) that
  steers Databricks-related prompts into the skills, a SessionStart context
  primer (`databricks-context.py`), and a PostToolUse auth-failure hinter
  (`databricks-auth-helper.py`), wired via `hooks/hooks.json`. All
  stdlib-only and fail-open. See [hooks/README.md](./hooks/README.md).
- `commands/`: friction-only slash commands (`/databricks:setup`,
  `/databricks:doctor`). Product workflows stay in the skills, not commands, to
  avoid shadowing a skill of the same name.

`python3 scripts/skills.py validate` checks these (hooks.json is valid and
references existing scripts, plugin.json does not double-declare hooks, every
command has frontmatter). After changing hook behavior, run the hook test
suite: `python3 -m unittest discover -s tests -p '*_test.py'`.
These ship via the plugin marketplace
(whole-repo source); `databricks aitools install` currently installs skills only.

**Marketplace entries are load-bearing for installed plugins.** Never remove a
shipped plugin's entry from `.claude-plugin/marketplace.json` (and never rename
the plugin or the marketplace). Claude Code re-resolves installed plugins
against the marketplace catalog at load time, so removing the entry does not
just stop updates: every existing install immediately fails to load ("Plugin
databricks not found in marketplace databricks-agent-skills") and those users
lose all skills, hooks, and commands until they manually uninstall and
reinstall from another source. Verified empirically (2026-06). Listing the
plugin on an additional marketplace, such as Anthropic's official directory,
is additive and never replaces the entry here.

## Security

When documenting examples, obfuscate sensitive info:

- Workspace IDs: use `1111111111111111` not real IDs
- URLs: use `company-workspace.cloud.databricks.com`
- Never include real tokens, passwords, credentials
- Use placeholders for users, teams, resource IDs
