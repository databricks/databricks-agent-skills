# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, Cursor, etc.) that provide Databricks-specific guidance.

## Installation

Two install paths cover the **stable** skills. They install to different places
but end up loaded by the same agents — pick whichever fits your workflow.

- **Databricks CLI** writes SKILL.md files directly into each agent's skill
  directory (`~/.claude/skills/`, `~/.cursor/extensions/<...>`, etc.).
- **Plugin marketplaces** (Claude Code, Cursor) cache the plugin under the
  agent's plugin directory (e.g. `~/.claude/plugins/cache/databricks-skills/`);
  the agent discovers skills from there.

**Via the Databricks CLI (canonical; supports experimental skills):**

```bash
databricks aitools install
```

The CLI auto-detects your coding agent(s) and installs the stable skills to the
right location:

- **Claude Code** → `~/.claude/skills/`
- **Cursor**, **Codex CLI**, **OpenCode**, **GitHub Copilot**, **Antigravity**
  → their respective skill directories

For finer control, use the `aitools skills install` subcommand directly — it
accepts a positional skill name and an `--experimental` flag (see the
[Experimental Skills](#experimental-skills) section).

**Via the Claude Code plugin marketplace** (stable skills only — installs every
skill under [`./skills/`](./skills/)):

```text
/plugin marketplace add databricks/databricks-agent-skills
/plugin install databricks-skills
```

**Via the Cursor plugin marketplace:**

```text
/add-plugin databricks-skills
```

### CLI vs plugin marketplace

| | CLI | Plugin marketplace |
|---|---|---|
| Stable skills | ✅ (default) | ✅ |
| Experimental skills | ✅ (with `--experimental` or by name) | ❌ |
| Per-skill selection | ✅ (`databricks aitools install <name>`) | ❌ (all-or-nothing) |
| Updates | `databricks aitools update` | Plugin marketplace update flow |
| Required outside the agent | Databricks CLI v1.0.0+ | None |

If in doubt, use the CLI — it's the canonical install path and the only one that
exposes experimental skills.

## Available Skills

Stable skills shipped from [`skills/`](./skills/):

- **databricks-core** — CLI, authentication, profile selection, data exploration. Parent skill for all product skills.
- **databricks-apps** — Build full-stack TypeScript apps on Databricks using AppKit.
- **databricks-dabs** — Declarative Automation Bundles (formerly Asset Bundles) for deploying and managing Databricks resources.
- **databricks-jobs** — Lakeflow Jobs orchestration: task types, triggers, schedules, notifications.
- **databricks-lakebase** — Lakebase Postgres: projects, branching, autoscaling, synced tables, Data API.
- **databricks-model-serving** — Model Serving endpoint management, AI Gateway, traffic config.
- **databricks-pipelines** — Lakeflow Spark Declarative Pipelines (formerly DLT) for batch and streaming.
- **databricks-serverless-migration** — Migrate classic-compute workloads to serverless compute.

## Experimental Skills

The [`experimental/`](./experimental/) directory contains additional skills
imported from [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
on a **best-effort basis**.

- Experimental skills are **not officially supported** — they may be used, but
  do not follow the same review / quality bar as the stable skills under
  [`skills/`](./skills/).
- They are **not installed by default** by `databricks aitools install`.
  Pass `--experimental` to install all of them, or install a specific one
  by name (with the `--experimental` flag — e.g. `databricks aitools install
  databricks-iceberg --experimental`).
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

For a narrower variation of an existing skill, create a subskill that declares
its parent via frontmatter. This is how the stable skills are organized today
— each product skill sets `parent: databricks-core`.

```markdown
---
name: "databricks-apps-chatbots"
description: "Databricks apps with chatbot features"
parent: databricks-apps
---

# Chatbot Apps

**FIRST**: Use the parent `databricks-apps` skill for app development basics.

Then apply these patterns:
- Pattern 1
- Pattern 2
```

This approach:
- Keeps the main skill stable and focused
- Allows experimentation without modifying core skills
- Makes it easy to follow the changes in the main skill

### Manifest Management

`manifest.json` is **generated** by `scripts/skills.py` from the skill directories and frontmatter. Do not edit it by hand. CI rejects manual changes via two checks: content drift (parsed dict doesn't match what `generate` would produce) and canonical form (on-disk bytes don't match `json.dumps(..., indent=2, sort_keys=True)`).

Sync assets and regenerate the manifest after adding or updating skills:

```bash
python3 scripts/skills.py
```

Validate that assets and manifest are up to date (used by CI):

```bash
python3 scripts/skills.py validate
```

The manifest is consumed by the CLI to discover available skills.

## Security

Please see [SECURITY](./SECURITY) for vulnerability reporting guidelines.

## Integrity

All future release tags will be GPG-signed and verifiable via `git tag -v <tag>`.

## Contributing

- All changes require approval from a code owner (see [CODEOWNERS](./.github/CODEOWNERS)).
- Documentation examples must follow least-privilege defaults — avoid suggesting elevated permissions or broad scopes unless explicitly necessary.
