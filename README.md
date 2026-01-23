# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, etc.) that provide Databricks-specific guidance.

## Installation

```bash
databricks experimental aitools skills install
```

This installs skills to `~/.claude/skills/` for use with Claude Code.

## Available Skills

- **databricks-apps** - Build full-stack TypeScript apps on Databricks using AppKit

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
name: "my-custom-databricks-apps"
description: "Databricks apps with custom patterns"
---

# Custom Databricks Apps

First, load the base databricks-apps skill for foundational guidance.

Then apply these additional patterns:
- Custom pattern 1
- Custom pattern 2
```

This approach:
- Keeps the main skill stable and focused
- Allows experimentation without modifying core skills
- Makes it easy to test variations and compare results
- Can be promoted to the main skill if proven valuable

### Manifest Management

Generate manifest after adding/updating skills:

```bash
python3 scripts/generate_manifest.py
```

Validate that manifest is up to date (for CI):

```bash
python3 scripts/generate_manifest.py validate
```

The manifest is used by the CLI to discover available skills.
