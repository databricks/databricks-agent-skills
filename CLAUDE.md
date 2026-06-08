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
python3 scripts/skills.py              # sync Codex metadata + icons, then generate manifest (default)
python3 scripts/skills.py sync         # sync Codex metadata + icons only
python3 scripts/skills.py validate     # check Codex metadata + icons + manifest are up to date (CI)
```

## Plugin components (hooks + commands)

Beyond skills, the Claude Code plugin ships two component dirs at the repo root.
`commands/` is declared via `"commands"` in `.claude-plugin/plugin.json`, but
**`hooks/hooks.json` is auto-loaded by Claude Code and must NOT be declared**
there — declaring the standard path double-loads it and fails the plugin with a
"Duplicate hooks file" error.

- `hooks/` — a UserPromptSubmit prompt router (`databricks-router.py`) that
  steers Databricks-related prompts into the skills, and a SessionStart context
  primer (`databricks-context.py`), wired via `hooks/hooks.json`. Both
  stdlib-only and fail-open. See [hooks/README.md](./hooks/README.md).
- `commands/` — friction-only slash commands (`/databricks:setup`,
  `/databricks:doctor`). Product workflows stay in the skills, not commands, to
  avoid shadowing a skill of the same name.

`python3 scripts/skills.py validate` checks these (hooks.json is valid and
references existing scripts, plugin.json does not double-declare hooks, every
command has frontmatter). Run `python3 hooks/databricks_router_test.py` after
changing the router's keyword lists. These ship via the plugin marketplace
(whole-repo source); `databricks aitools install` currently installs skills only.

## Security

When documenting examples, obfuscate sensitive info:

- Workspace IDs: use `1111111111111111` not real IDs
- URLs: use `company-workspace.cloud.databricks.com`
- Never include real tokens, passwords, credentials
- Use placeholders for users, teams, resource IDs
