# Databricks Agent Skills

Skills for AI coding assistants (Claude Code, Cursor, etc.) that provide Databricks-specific guidance.

## Installation

Two install paths cover the **stable** skills. They install to different places
but end up loaded by the same agents — pick whichever fits your workflow.

- **Databricks CLI** writes SKILL.md files directly into each agent's skill
  directory (`~/.claude/skills/`, `~/.cursor/extensions/<...>`, etc.).
- **Plugin marketplaces** (Claude Code, Cursor) cache the plugin under the
  agent's plugin directory (e.g. `~/.claude/plugins/cache/databricks-agent-skills/`);
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
/plugin install databricks@databricks-agent-skills
```

**Via the Cursor plugin marketplace:**

```text
/add-plugin databricks
```

The Cursor plugin ships the skills plus the `databricks-setup` /
`databricks-doctor` commands, two of the three hooks (session context,
auth-failure hints), and a routing rule that steers Databricks prompts into the
skills; see
[Commands and hooks](#commands-and-hooks-claude-code-cursor).

**Via the GitHub Copilot plugin marketplace:**

```text
copilot plugin marketplace add databricks/databricks-agent-skills
copilot plugin install databricks@databricks-agent-skills
```

Works in Copilot CLI (plugins are GA there) and VS Code (agent plugins,
preview; also installable from the Extensions view). Ships the skills plus
two hooks: the session context primer and the auth-failure hinter (both run on
Copilot CLI and the cloud agent; VS Code has its own hooks system). The Copilot
cloud agent on github.com takes no plugins;
for that surface, vendor the skills into the target repo (`.github/skills/`)
and the auth-hint hook into `.github/hooks/`.

**Via the Codex plugin marketplace:**

```text
codex plugin marketplace add databricks/databricks-agent-skills
codex plugin add databricks
```

The Codex plugin ships the skills plus all three hooks (prompt routing,
session context, auth-failure hints). Codex hash-pins plugin hooks: run
`/hooks` once after install (and after each update) to review and enable
them. Codex has no distributable slash commands, so the setup/doctor
workflows are reachable through the skills there.

### CLI vs plugin marketplace

| | CLI | Plugin marketplace |
|---|---|---|
| Stable skills | ✅ (default) | ✅ |
| Experimental skills | ✅ (with `--experimental` or by name) | ❌ |
| Per-skill selection | ✅ (`databricks aitools install <name>`) | ❌ (all-or-nothing) |
| Commands & hooks | ❌ (skills only today, see below) | ✅ |
| Updates | `databricks aitools update` | Plugin marketplace update flow |
| Required outside the agent | Databricks CLI v1.0.0+ | None |

If in doubt, use the CLI — it's the canonical install path and the only one that
exposes experimental skills.

## Available Skills

Stable skills shipped from [`skills/`](./skills/):

- **databricks-core** — CLI, authentication, profile selection, data exploration. Parent skill for all product skills.
- **databricks-apps** — Build full-stack TypeScript apps on Databricks using AppKit.
- **databricks-app-design** — Design the UX of data apps: dashboards, KPI pages, reports, charts, and Genie/chat surfaces, mapped to AppKit components.
- **databricks-dabs** — Declarative Automation Bundles (formerly Asset Bundles) for deploying and managing Databricks resources.
- **databricks-jobs** — Lakeflow Jobs orchestration: task types, triggers, schedules, notifications.
- **databricks-lakebase** — Lakebase Postgres: projects, branching, autoscaling, synced tables, Data API.
- **databricks-model-serving** — Model Serving endpoint management, AI Gateway, traffic config.
- **databricks-pipelines** — Lakeflow Spark Declarative Pipelines (formerly DLT) for batch and streaming.
- **databricks-serverless-migration** — Migrate classic-compute workloads to serverless compute.
- **databricks-vector-search** — Vector Search endpoints + indexes for RAG and semantic search.

## Experimental Skills

The [`experimental/`](./experimental/) directory contains additional skills
originally imported from
[databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
(now deprecated — this repo is the source of truth going forward) on a
**best-effort basis**.

- Experimental skills are **not officially supported** — they may be used, but
  do not follow the same review / quality bar as the stable skills under
  [`skills/`](./skills/).
- They are **not installed by default** by `databricks aitools install`.
  Pass `--experimental` to install all of them, or install a specific one
  by name (with the `--experimental` flag — e.g. `databricks aitools install
  databricks-iceberg --experimental`).
- See [`experimental/README.md`](./experimental/README.md) for the full list
  and caveats.

## Commands and hooks (Claude Code, Cursor)

When installed as a Claude Code plugin, the `databricks` plugin adds slash
commands and three hooks (prompt routing, session context, auth-failure hints)
on top of the skills. The Cursor plugin (`databricks`) ships the same
commands and two of the hooks; see the Cursor note below.
(These ship via the plugin marketplaces; the CLI `databricks aitools install`
path installs skills only today; see the note at the end.)

**Slash commands**: friction-only entry points; everyday work stays with the
auto-invoked skills.

- `/databricks:setup [workspace-url]`: auth/onboarding. Install check, then an
  OAuth / PAT / service-principal profile, then verify.
- `/databricks:doctor [profile]`: read-only health check (CLI version, auth,
  workspace reachability, compute, recent job failures).

(Product workflows such as apps, jobs, pipelines, DABs, etc. are handled by the
skills, not commands, so they aren't duplicated here.)

**Hooks** (`hooks/`, all fail-open):

- **Prompt router** (UserPromptSubmit): a fast keyword regex (sub-50ms, no LLM,
  no network) over each prompt. When the prompt is Databricks-related, it injects
  a note steering Claude to load `databricks-core` plus the matching product
  skill before answering. The full note fires once per session; later Databricks
  prompts get a one-line reminder. Unrelated prompts are untouched. No
  permission gating, no cost warnings.
- **Context primer** (SessionStart, skipped on resume): injects the routing
  rule, CLI version, configured profile names and any
  `[__settings__].default_profile` (read locally, no network call, no token
  values), and env/in-platform auth state.
- **Auth-failure hint** (PostToolUse on Bash): when a `databricks` command fails
  with an auth-shaped error, adds one line suggesting `/databricks:doctor` or
  `databricks auth login` before retrying. Never blocks or rewrites commands.

**Cursor.** Cursor has a flat `/` menu (no `plugin:command` namespacing), so
the same commands ship as `/databricks-setup` and `/databricks-doctor` from
[`commands-cursor/`](./commands-cursor/). Hooks are wired via
[`hooks/cursor-hooks.json`](./hooks/cursor-hooks.json) (declared explicitly in
`.cursor-plugin/plugin.json`): the context primer (`sessionStart`) and the
auth-failure hint (`postToolUse`), both invoked with `--platform cursor` so
they emit Cursor's output shape and reference the Cursor command names. The
prompt-router hook does not port (Cursor's `beforeSubmitPrompt` cannot inject
context), so routing instead ships as a Cursor rule
([`rules/databricks-routing.mdc`](./rules/databricks-routing.mdc)) that injects
the routing table when a prompt is Databricks-related, independent of an open
Cursor bug that currently drops hook `additional_context`. Native skill
selection also helps.

> **Distribution parity (follow-up).** The plugin marketplace ships the whole
> repo (`marketplace.json` `source: "./"`), so commands and hooks come with it.
> `databricks aitools install` currently packages only `skills/`, so CLI-install
> users don't yet get commands/hooks. Closing that gap is tracked as CLI-side
> work.

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

### Plugin manifest management

The repo ships one plugin to four targets (Claude Code, Codex, Copilot, Cursor)
plus three marketplace catalogs. Their `plugin.json` / `marketplace.json` files
are **generated** from a single source of truth,
[`plugin.meta.json`](./plugin.meta.json), by `scripts/skills.py`. Do not
hand-edit the generated files (each generated directory also carries a
`README.md` saying so) — edit `plugin.meta.json` and regenerate:

```bash
python3 scripts/skills.py generate   # regenerates manifest.json + all plugin manifests
python3 scripts/skills.py validate   # CI check: fails on any drift
```

`plugin.meta.json` owns the version (one value, propagated to all four targets),
name, description, keywords, author/license, per-target display names and
hook/command/rule wiring, and the skill-to-keyword map. Adding a stable skill
means adding it to the `skills` map there (with a `keyword`); CI fails if a
shipped skill has no entry. See
[CONTRIBUTING.md](./CONTRIBUTING.md) for the full field reference.

## Security

Please see [SECURITY](./SECURITY) for vulnerability reporting guidelines.

## Integrity

Release tags are created by the [Release workflow](./.github/workflows/release.yml)
and map 1:1 to a published version.

## Contributing

- All changes require approval from a code owner (see [CODEOWNERS](./.github/CODEOWNERS)).
- Documentation examples must follow least-privilege defaults — avoid suggesting elevated permissions or broad scopes unless explicitly necessary.
