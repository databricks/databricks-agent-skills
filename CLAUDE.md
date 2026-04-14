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

### Skills management

```bash
python3 scripts/skills.py              # sync assets + generate manifest (default)
python3 scripts/skills.py sync         # copy shared assets into each skill dir
python3 scripts/skills.py validate     # check assets + manifest are up to date (CI)
```

## Security

When documenting examples, obfuscate sensitive info:

- Workspace IDs: use `1111111111111111` not real IDs
- URLs: use `company-workspace.cloud.databricks.com`
- Never include real tokens, passwords, credentials
- Use placeholders for users, teams, resource IDs
