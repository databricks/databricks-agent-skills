# Install this skill in a Databricks workspace (Genie Code Agent mode)

You can run this skill **inside Databricks** — not just from Claude Code or Cursor on your laptop. Databricks Genie Code Agent mode uses the same Agent Skills standard ([agentskills.io](https://agentskills.io/specification)) as Claude Code, so this skill is drop-in compatible. Once installed, the skill auto-loads in Genie Code Agent chats based on its `description` frontmatter, or you can invoke it explicitly.

## Where skills live in a workspace

Workspace files at one of two paths:

| Scope | Path | Who can install |
|-------|------|-----------------|
| **Per-user** | `/Workspace/Users/<your-email>/.assistant/skills/<skill-name>/` | Any user |
| **Workspace-wide** | `/Workspace/.assistant/skills/<skill-name>/` | Workspace admin only |

Genie Code automatically picks up skills from these paths the next time the user starts an Agent-mode chat — no manifest registration, no separate UI step.

## Three install methods

### Option 1 — Notebook installer (easiest for one user)

The `databricks-solutions/ai-dev-kit` repo ships a notebook that pulls skills from GitHub and writes them to your `/Workspace/Users/<you>/.assistant/skills/` path.

1. Import [`install_genie_code_skills.py`](https://github.com/databricks-solutions/ai-dev-kit/blob/main/databricks-skills/install_genie_code_skills.py) into your workspace.
2. Edit the constants at the top of the notebook:
   - `REPO = "databricks/databricks-agent-skills"`
   - `BRANCH = "main"`
   - `SKILLS = ["databricks-serverless-migration"]` (plus any others you want)
3. Attach the notebook to any running cluster (classic or serverless, any size).
4. Run All. The installer uses `WorkspaceClient().workspace.import_()` to upload `SKILL.md` + every file listed in this skill's entry in `manifest.json`.
5. Open a Genie Code Agent chat. The skill loads on demand based on its `description`.

### Option 2 — Shell installer (for repeat installs)

From a local clone of `databricks-solutions/ai-dev-kit`:

```bash
./databricks-skills/install_skills.sh --local --install-to-genie
```

Add `--profile <YOUR_PROFILE>` if your `databricks` CLI default isn't the target workspace. Requires the `databricks` CLI installed and authenticated locally.

### Option 3 — Databricks App (workspace-wide)

The `mcp-ai-dev-kit` app deploys once per workspace, pulls skills from a configured GitHub repo on every redeploy, and writes to the workspace-wide `/Workspace/.assistant/skills/` path so every user in the workspace sees them. Recommended if you're rolling this skill out to a team.

This requires workspace admin. Ask the workspace admin who owns the Databricks Apps deployment for your workspace, or refer to the public Databricks Apps documentation.

## Format compatibility

Zero conversion needed. Genie Code uses the same Agent Skills layout as Claude Code:

```
databricks-serverless-migration/
├── SKILL.md          # frontmatter + instructions (this skill)
├── agents/           # optional agent configs
├── assets/           # static assets
└── references/       # supplementary docs loaded on demand (you're reading one)
```

The installer copies the entire skill directory as listed in `manifest.json`.

## Caveats specific to this skill

⚠️ **Databricks CLI is not pre-installed on serverless compute.** This skill's frontmatter declares `compatibility: Requires databricks CLI (>= v0.292.0)` because several recommended commands shell out to `databricks bundle deploy`, `databricks jobs update`, and `databricks fs cp`.

Inside Genie Code on serverless compute, those commands will fail with `databricks: command not found`. Three options to reconcile:

1. **Run the Agent-mode chat against a classic cluster** that has the CLI installed (you can `%pip install databricks-cli` in a setup cell, or bake it into a cluster init script).
2. **Use the Databricks SDK equivalents** the skill mentions where available — `WorkspaceClient().jobs.update(...)`, `WorkspaceClient().workspace.import_(...)`. The skill's recommendations are CLI-flavored today; SDK calls work equivalently in a notebook context.
3. **Skip the deploy steps** entirely. The skill's value is the analyze + migrate phases — code transformation, blocker detection, and fix suggestions. Those work without the CLI. You can apply the migrated job/DABs changes by hand or from a separate environment.

Other notes:

- **Genie Code's underlying model is not publicly specified** and may not be Claude. The skill is authored against Claude Code defaults; behavior parity is not guaranteed. Smoke-test on a non-critical workload first.
- **Skills are knowledge + scripts, not arbitrary tools.** Genie Code skills can't make network calls outside the workspace boundary. The skill's GitHub-issue-filing flow ([Failure Reporting](failure-reporting.md)) still works because it generates a URL the user clicks rather than auto-submitting.
- **File-edit sandboxing**: Genie Code can write files in the workspace, so the migration outputs (migrated notebooks, updated job JSON, env spec YAML) land where you expect.

## Pointers and follow-ups

| Resource | Link |
|----------|------|
| Public docs: Extend Genie Code with agent skills | https://docs.databricks.com/en/genie-code/skills |
| Public docs: Agent skills overview | https://docs.databricks.com/en/agent-skills/ |
| Notebook + shell installer | https://github.com/databricks-solutions/ai-dev-kit |
| This skill's source | https://github.com/databricks/databricks-agent-skills/tree/main/skills/databricks-serverless-migration |
| Agent Skills spec | https://agentskills.io/specification |

For runtime questions or to report skill issues, file an issue on the public skill repo: https://github.com/databricks/databricks-agent-skills/issues
