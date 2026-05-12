# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, Cursor, etc.) that provide Databricks-specific guidance.

## Installation

**For Claude Code:**

```bash
databricks experimental aitools install
```

This installs skills to `~/.claude/skills/` for use with Claude Code.

**For Cursor:**

Run this command in chat:

```text
/add-plugin databricks-skills
```

## Available Skills

- **databricks-apps** - Build full-stack TypeScript apps on Databricks using AppKit

See [`skills/`](./skills/) for the full list of supported skills.

## Experimental Skills

The [`experimental/`](./experimental/) directory contains additional skills
imported from [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
on a **best-effort basis**.

- Experimental skills are **not officially supported** — they may be used, but
  do not follow the same review / quality bar as the stable skills under
  [`skills/`](./skills/).
- They are **not installed by default** by `databricks experimental aitools
  skills install`. Pass `--experimental` to install all of them, or install
  a specific one by name (with the `-experimental` suffix and the flag —
  e.g. `databricks-iceberg-experimental --experimental`).
- See [`experimental/README.md`](./experimental/README.md) for the full list
  and caveats.

## Structure

Each skill follows the [Agent Skills Specification](https://agentskills.io/specification):

```
skill-name/
├── SKILL.md           # Main skill file with frontmatter + instructions
└── references/        # Additional documentation loaded on demand
```

## Development

### Adding New Skills

When experimenting with new skill variations, create a "subskill" that references the main skill and adds specific guidance:

```markdown
---
name: "ai-databricks-apps"
description: "Databricks apps with AI features"
---

# AI powered Databricks Apps

First, load the base databricks-apps skill for foundational guidance.

Then apply these additional patterns:
- Custom pattern 1
- Custom pattern 2
```

This approach:
- Keeps the main skill stable and focused
- Allows experimentation without modifying core skills
- Makes it easy to follow the changes in the main skill

### Manifest Management

Sync assets and generate manifest after adding/updating skills:

```bash
python3 scripts/skills.py
```

Validate that assets and manifest are up to date (for CI):

```bash
python3 scripts/skills.py validate
```

The manifest is used by the CLI to discover available skills.

## Security

Please see [SECURITY](./SECURITY) for vulnerability reporting guidelines.

## Integrity

All future release tags will be GPG-signed and verifiable via `git tag -v <tag>`.

## Contributing

- All changes require approval from a code owner (see [CODEOWNERS](./.github/CODEOWNERS)).
- Documentation examples must follow least-privilege defaults — avoid suggesting elevated permissions or broad scopes unless explicitly necessary.
