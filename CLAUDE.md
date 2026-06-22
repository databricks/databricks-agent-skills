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

## Plugin manifests (generated from `metaplugin/plugin.meta.json`)

Each agent fetches its own **per-provider** bundle under
`plugins/databricks/<provider>/` (`claude/`, `codex/`, `copilot/`, `cursor/`).
Every folder is fully generated and self-contained, holding only what that
provider uses: its `plugin.json`, a copy of `skills/`, the hook wiring it needs
(plus the referenced `*.py` scripts and, where the router is wired, `_routing_data.json`),
and — only where applicable — `commands/` (Claude, Cursor), `rules/` (Cursor),
and `assets/` (Codex's interface logo). At the repo root, four `marketplace.json`
catalogs (`.claude-plugin/`, `.github/plugin/`, `.agents/plugins/`,
`.cursor-plugin/` — Cursor's is new) each point a **scoped source** at *its own*
provider subfolder (`plugins/databricks/<provider>`), so an install fetches only
that provider's payload. The catalogs currently track `main`; a mechanical
follow-up flips them to tag-pinning. The bundles, the catalogs, every
`plugin.json`, the hook wiring, the routing files, the rendered commands, and
`manifest.json` are all **generated** from
[`metaplugin/plugin.meta.json`](./metaplugin/plugin.meta.json) (and the templated
`commands/` source) by `scripts/skills.py generate`. **Do not hand-edit them** —
edit the source and regenerate. (Each generated manifest dir carries a `README.md`
marker; `plugins/**` is marked `linguist-generated` so the bundle stays out of
review noise.) CI (`validate`) fails on any drift, including a bundle that does
not match a fresh build. The version lives only in `metaplugin/plugin.meta.json`
and propagates to all four targets. Adding a stable skill requires an entry in
the `skills` map (with a `keyword`).

Everything under `plugins/` is generated, committed, and drift-checked (it is not
gitignored in this repo). The catalogs' scoped source is configured under
`marketplace.source` in `metaplugin/plugin.meta.json`; ref-capable tools
(Claude, Codex, Copilot) pin `v{version}` release tags instead of main HEAD.
Cursor cannot pin a ref and always tracks the default
branch. The CLI's raw-skills (files-channel) installer is unaffected — it keeps
fetching the root `skills/`, so the manifest's stable `repo_dir` stays `skills`.

The generator itself lives in `scripts/skillsgen/` (a package split by concern:
plugins, routing, hooks, validators, ...); `scripts/skills.py` is a thin façade
that re-exports it and is the CLI entry point.

The `routing` block in `metaplugin/plugin.meta.json` is generated too: it renders the
prompt router's data (`hooks/_routing_data.json`, loaded by
`hooks/databricks-router.py`) and the Cursor rule
(`rules/databricks-routing.mdc`) from one table. Do not hand-edit those; edit
`metaplugin/plugin.meta.json` and regenerate. CI fails if a product skill has no routing row.

The four hook-wiring files (`hooks/hooks.json`, `codex-hooks.json`,
`copilot-hooks.json`, `cursor-hooks.json`) are also generated, from the `hooks`
block + each target's `hooks_render`. Edit `metaplugin/plugin.meta.json` and regenerate;
the hook `*.py` scripts stay hand-written, only the wiring JSON is generated.

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
These ship via the plugin marketplace inside the `plugins/databricks/` bundle
(each catalog points a scoped source at it); `databricks aitools install`
currently installs skills only.

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
