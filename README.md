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

Generate manifest after adding/updating skills:

```bash
python3 scripts/generate_manifest.py
```

The manifest is used by the CLI to discover available skills.
