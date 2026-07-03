# Contribute to Public Agent Skills

## TLDR

Public Agent Skills for Claude Code, Codex, Cursor, and other third-party coding agents are published through the public repo [databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills).

They are available, as of June 24, 2026, in the official Claude Code Marketplace and Cursor Marketplace. We also have local marketplaces for Codex and GitHub Copilot. The public GitHub repo is read-only for Databricks-authored contributions. To contribute, go to [`oss/repos/databricks-agent-skills`](https://sourcegraph.prod.databricks-corp.com/databricks-eng/universe/-/tree/oss/repos/databricks-agent-skills) in `databricks-eng/universe` and open a PR.

## Contributing

If you want to write a new skill or improve a skill, this section is for you. Any changes to the skills must happen in the `databricks-eng/universe` repo, in the directory `oss/repos/databricks-agent-skills`. We recommend doing a sparse checkout if you just work on the DAS skill.

**Important: branches must be created on universe-dev, and PR sent on universe.**

We have an automated pipeline that will push changes from `universe` to the public `databricks-agent-skills` repository nightly. Once changes are pushed, they will be published in a release from the public repository and our customers can use them.

If you don't already have access to Universe:

- If you don't have an EMU GitHub account already, request [`app.github-emu.default-permissions`](https://app.opal.dev/groups/799b4948-6560-462b-b8f3-870ad78b3d6c) in Opal. Once approved, the GitHub EMU tile appears in Okta.
- For field to get write access, request this Opal group: [`github-emu-team.eng.fieldeng-universe-write`](https://app.opal.dev/groups/a8e0dc8b-1dc5-4d75-8c8d-19e87f0462da).
- Product managers should request this Opal group: [`github-emu-team.eng.all-pm`](https://app.opal.dev/groups/c5840a7c-3382-48e2-8e14-4ae4e5e7f2a4).

## Stable Skill Workflow

A stable skill belongs in `skills/` when the product team is ready for it to install by default and to shape agent behavior for all users. This is the path for well-owned product skills, shared platform skills, or updates to an existing stable skill.

1. Create or edit `skills/databricks-<name>/SKILL.md`.
2. Add supporting markdown under `skills/databricks-<name>/references/` when the skill needs details that should load on demand.
3. For a new stable skill, add the skill to the `skills` map in `metaplugin/plugin.meta.json` with a marketplace `keyword`.
4. For a new product skill, add a row to the `routing.table` in `plugin.meta.json` so prompt routing and the Cursor rule know when to load it.
5. Run `python3 scripts/skills.py generate` from `oss/repos/databricks-agent-skills`.
6. Run `python3 scripts/skills.py validate`.
7. Ask a skill champion and the owning product team to review the behavior, not just the wording.

Every skill ships the same logical shape, whether stable or experimental:

```text
<skill>/
|-- SKILL.md
|-- references/*.md
|-- agents/openai.yaml
`-- assets/
    |-- databricks.svg
    `-- databricks.png
```

`SKILL.md` is the instruction file every agent reads. `agents/openai.yaml` is Codex marketplace metadata. The Databricks icons are copied from the repo root. `scripts/skills.py generate` creates missing Codex metadata and icons, regenerates `manifest.json`, and renders plugin artifacts from `metaplugin/plugin.meta.json`; do not hand-edit generated output.

Use frontmatter like this for a new product skill:

```markdown
---
name: databricks-foo
description: Databricks Foo workflows
parent: databricks-core
---

# Databricks Foo

Use `databricks-core` first for authentication, profile selection, and CLI basics.
```

Most product skills should declare `parent: databricks-core`. Use a narrower parent only when the new skill is truly a specialized variant of another stable skill.

## Experimental Skill Workflow

If you are releasing a new skill with little evidence how well it works, it is a judgement call whether to first release it in `/experimental` or immediately graduate it to `/skills`. The best you can do is run evals if that is possible, while we do understand that is not always the case.

If a skill covers an existing or older product, you run the risk of making the third-party agent's performance worse than what it knows from the training data. In this case, less is often more and a small focused skill can be a better starting point than a large verbose skill.

If it's a brand new product that the third-party agent wouldn't know anything about, then the case for the skill is probably more clear cut.

Use `experimental/` when a skill is useful enough to share but does not yet have the evidence, ownership, or quality bar required for default installs.

1. Create `experimental/<skill>/SKILL.md`.
2. Add `references/` only for material that is too detailed for the main skill file.
3. Run `python3 scripts/skills.py generate`.
4. Run `python3 scripts/skills.py validate`.
5. Document any caveats in the experimental skill itself and update `experimental/README.md` if the list or positioning changes.

Experimental skills are not installed by default:

```bash
databricks aitools install --experimental
databricks aitools install databricks-genie --experimental
```

To graduate an experimental skill into `skills/`, first show that it improves the intended customer journeys without degrading adjacent skills. When eval coverage exists, add or update the relevant evals and include the before/after result in the PR. Then move the skill to `skills/`, add plugin metadata and routing, regenerate, validate, and get champion review.

### Review - Skill Champions

v1:

- [Simon Faltum](mailto:simon.faltum@databricks.com)
- [Dustin Vannoy](mailto:dustin.vannoy@databricks.com)
- [Cal Reynolds](mailto:cal.reynolds@databricks.com)
- [Quentin Ambard](mailto:quentin.ambard@databricks.com)
- [Malcoln Dandaro](mailto:malcoln.dandaro@databricks.com)
- [Jack Sandom](mailto:jack.sandom@databricks.com)

Each skill that is owned by a product team, that product team will also have the responsibility to have a skill champion.

v2:

Must onboard and specify skill champions from each product team where applicable.

## Authoring Bar

A skill should push the agent toward durable Databricks outcomes, not one-off chat output. When a request can be satisfied several ways, prefer this order:

1. Call a Databricks agent or product-native assistant when one owns the workflow.
2. Create a governed workspace asset with permissions, lineage, and audit.
3. Use Databricks platform primitives such as Lakeflow Declarative Pipelines, Unity Catalog, Auto CDC, MLflow, Declarative Automation Bundles, Vector Search, Online Tables, or Model Serving.
4. Run raw SQL, schema inspection, or extraction only as scaffolding or as the last reasonable option.

For third-party coding agents, prefer the Databricks CLI when possible. When code is required, prefer official SDKs and supported frameworks: JavaScript/TypeScript, Java, Python, Go, and AppKit where applicable. Avoid undocumented public APIs unless the skill is explicitly documenting an internal-only or experimental workflow and states that caveat.

Keep skills focused. For an older or widely documented product, a large skill can make an agent worse by overriding useful pretrained knowledge with noisy instructions. Start with the smallest instruction set that fixes known failures. For a new product that agents cannot know from training data, a broader baseline skill is usually easier to justify.

## Distribution

The CLI installs the **databricks plugin** through each agent's own CLI when the agent supports a headless plugin install. Agents without one get **raw skill files** instead. You don't choose this per agent; it's automatic:

| Agent | Delivery | Notes |
| :-- | :-- | :-- |
| Claude Code | plugin | Installs from Claude's built-in `claude-plugins-official`. |
| Codex CLI | plugin | Installs from the `databricks-agent-skills` marketplace. |
| GitHub Copilot | plugin | Installs from the `databricks-agent-skills` marketplace. |
| Cursor | skills | No headless plugin install; gets raw skill files. |
| OpenCode | skills | Raw skill files. |
| Antigravity | skills | IDE-only, no CLI; raw skill files. |

```bash
# Detect your agents and install (interactive picker on a TTY)
databricks aitools install
```

```bash
# See what's installed and whether updates are available
databricks aitools list
```

```bash
# Pull the latest release
databricks aitools update
```

```bash
# Remove everything (asks to confirm on a TTY)
databricks aitools uninstall
```

### Scope: global vs project

Two scopes, selected with `--scope` or prompted interactively:

- **global** (default) - available across all your projects. Skills: `~/.databricks/aitools/skills/`
- **project** - checked into the repo, shared with everyone on the project. Skills: `<cwd>/.databricks/aitools/skills/`

For **plugins**, project scope is only supported by agents that support it, Claude Code today. Other agents are skipped with a reason rather than silently installing to user scope.

```bash
databricks aitools install --scope=global     # default
databricks aitools install --scope=project    # install into the current repo
databricks aitools install --agents claude-code,cursor
```

### Claude Code

Terminal:

```bash
claude plugin install databricks@claude-plugins-official
```

In session:

```text
/plugin install databricks@claude-plugins-official
```

### Cursor plugin

Go to [https://cursor.com/marketplace/databricks](https://cursor.com/marketplace/databricks), or write `/add-plugin databricks` in Cursor chat.

**Only works in the IDE, not the CLI.**

### Codex

Terminal:

```bash
codex plugin marketplace add databricks/databricks-agent-skills
codex plugin add databricks
```

Inside the IDE:

```text
/plugin marketplace add databricks/databricks-agent-skills
/plugin install databricks@databricks-agent-skills
```

### Copilot

Terminal:

```bash
copilot plugin marketplace add databricks/databricks-agent-skills
copilot plugin install databricks@databricks-agent-skills
```

Inside the IDE:

```text
/plugin marketplace add databricks/databricks-agent-skills
/plugin install databricks@databricks-agent-skills
```

## Releases

We have a release workflow in GitHub: [release.yml](https://github.com/databricks/databricks-agent-skills/actions/workflows/release.yml).

When we run this workflow the following happens:

- Read release version from `version.meta.json`.
- Run the bump version action.
- Validate current skills, and generate plugins.
- Commit the release with generated plugins/files to the repo.
- Create annotated tag.
- Create GitHub release.

Plugins are mostly copies of skills plus a few transformed files, and we have a physical checked-in copy for each provider under `/plugins/databricks/{provider}`. The plugins folder is generated from `metaplugin/plugin.meta.json`; do not hand-edit it. Edit the source and run `python3 scripts/skills.py generate`.

### Claude Code Marketplace

Added here: [anthropics/claude-plugins-official#3243](https://github.com/anthropics/claude-plugins-official/pull/3243).

When we update the plugin version, Anthropic has a daily job that updates the SHA pin: [bump-plugin-shas.yml](https://github.com/anthropics/claude-plugins-official/blob/main/.github/workflows/bump-plugin-shas.yml).

**Contact**: Charmaine Lee

### Cursor Marketplace

Tracks head of main in [github.com/databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills).

**Contacts**: [Eric Zakariasson](mailto:eric@anysphere.co) and [Jason Ma](mailto:jma@anysphere.co)

### Codex Marketplace

We have a local marketplace for now, release is automated.

### Copilot Marketplace

We have a local marketplace for now, release is automated.

## Evals

Evals are not yet implemented. Once done, this section will contain instructions on how to run evals and how to add evals.

Once we have evals set up:

- Skill changes must not degrade existing evals.
- If improvements touch a CUJ that has no evals so far, the author should add new CUJ to evals and show how it is improved by the changes compared with baseline.

## Security And Examples

Skill examples must be safe to copy. Follow these defaults:

- Use least-privilege permissions; do not suggest `ALL PRIVILEGES` when a narrower grant works.
- State explicitly when an example requires elevated permissions such as workspace admin.
- Prefer scoped tokens over broad credentials.
- Use placeholder workspace IDs such as `1111111111111111`.
- Use placeholder workspace URLs such as `company-workspace.cloud.databricks.com`.
- Never include real tokens, passwords, private keys, customer identifiers, or internal credentials.
