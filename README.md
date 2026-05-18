# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, Cursor, etc.) that provide Databricks-specific guidance.

## Installation

**For Claude Code (as a plugin):**

```text
/plugin marketplace add databricks/databricks-agent-skills
/plugin install databricks-skills@databricks-agent-skills
```

**For Claude Code (via the Databricks CLI):**

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

- **databricks-core** — Databricks CLI: auth, profiles, data exploration
- **databricks-apps** — Build apps on the Databricks Apps platform with AppKit
- **databricks-dabs** — Declarative Automation Bundles (formerly Asset Bundles)
- **databricks-jobs** — Develop and deploy Lakeflow Jobs
- **databricks-lakebase** — Lakebase Postgres: projects, scaling, connectivity, synced tables
- **databricks-model-serving** — Create, configure, and query Model Serving endpoints
- **databricks-pipelines** — Lakeflow Spark Declarative Pipelines (formerly DLT)
- **databricks-serverless-migration** — Migrate workloads from classic compute to serverless

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
