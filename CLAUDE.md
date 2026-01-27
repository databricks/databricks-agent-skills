# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, etc.) that provide Databricks-specific guidance.

## Structure

```
skills/
├── databricks/           # core skill: CLI, auth, data exploration
│   ├── SKILL.md
│   └── *.md (references)
└── databricks-apps/      # product skill: app development
    ├── SKILL.md
    └── references/
```

Hierarchy: `databricks` (core) → `databricks-apps` (product) → `databricks-apps-*` (niche)

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

### Manifest

```bash
python3 scripts/generate_manifest.py           # generate
python3 scripts/generate_manifest.py validate  # check in CI
```

## Security

When documenting examples, obfuscate sensitive info:

- Workspace IDs: use `1111111111111111` not real IDs
- URLs: use `company-workspace.cloud.databricks.com`
- Never include real tokens, passwords, credentials
- Use placeholders for users, teams, resource IDs
