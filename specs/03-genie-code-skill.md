# Spec: `databricks-genie-code` skill

Closes GC-1 and GC-8. The repo ships nothing for `.assistant/skills/` and no
workspace-versus-user tier guidance, despite `docs.databricks.com/aws/en/agent-skills/`
pointing readers at the Genie Code pages as the sibling path. Four install
targets are supported today — Claude Code, Codex, Copilot, Cursor. Databricks'
own agent is not one of them.

Authoring task. Do not attempt it in the same branch as a mechanical sweep.

## Path

`skills/databricks-genie-code/` with `SKILL.md` and `references/`.

Follow the repo's documented new-skill workflow in `AGENTS.md`, including the
`metaplugin/plugin.meta.json` entry and `scripts/skills.py generate`.

## Structure

Per `specs/01-skill-structure.md`. H1, then exactly two H2s — `## Instructions`,
`## Examples`. Further structure at H3 beneath one of them.

## Frontmatter

- `name: databricks-genie-code`
- `description`, 300–500 chars, carrying what + when + a do-not-use-for clause
  naming **both** siblings. Genie is a three-product family: Genie Code
  (developers, this skill), Genie One (business users, simplified data chat),
  Genie Agents (curated trusted-data and business-rule environments). Without
  three-way disambiguation the skill fires on Genie Agents questions and answers
  them wrongly.
- `compatibility`: Genie Code is a Designated Service using Geos for data
  residency; the "Enforce data processing within workspace Geography for AI
  features" setting may need disabling before it can be enabled. State the
  dependency. Name no dates.
- `parent: databricks-core` to match sibling convention.

## `## Instructions` — six items

1. **Name the surface first.** Behaviour differs across notebooks, SQL editor,
   Lakeflow Pipelines Editor, AI/BI dashboards, and MLflow. The same prompt does
   not mean the same thing in each.
2. **One task per chat.** Full-page Genie Code supports parallel chats, so a
   fresh chat per task is cheap rather than a nuisance.
3. **Goal plus limits, not step-by-step.** Row caps on exploratory runs. Two
   rationales: correctness, and billable usage — Genie Code is pay-as-you-go
   with a per-user monthly allowance and admin-managed budgets. State the
   mechanism, never the dates.
4. **Unity Catalog grants are the real blast radius.** Genie Code can only
   access data and perform operations the caller has permission for. Scope the
   agent's identity to the intended blast radius; sandbox-schema instructions
   and per-action approval are secondary controls layered on top.
5. **Stop and redirect on a loop.** Forcefully stop generation and instruct in
   text rather than waiting out a repeated failed fix.
6. **Routing pointers** to both reference files, each with a stated load
   condition.

Composition table as an H3 under Instructions, not a third H2.

## `references/practice-guide.md`

H2 heading exactly: `## Databricks Genie Code Full Practice Guide & Examples`

Procedural rewrite in original words. The upstream source is a copyrighted
article — capture the rules, never the prose, and never a structural paraphrase.
One source line crediting it.

Two exclusions:
- Drop the Assistant-to-Genie-Code transition narrative entirely. Dated
  positioning, not procedure.
- Drop the browser-tab-pause mechanic. Not doc-supported; the docs say chats
  persist as you navigate between pages, which is a different claim.

## `references/troubleshooting.md`

H3 heading exactly: `### Troubleshooting`

Genie Code failure modes only, symptom → fix. The infinite-execution-loop item
is the one native to this surface.

Close with a single pointer: the misunderstood-business-jargon and
incorrect-joins remedies (UC table and column comments, explicit foreign-key
relationships, knowledge store) belong to **Genie Agents**, with its docs URL.
Do not present them as Genie Code remedies.

Drop the `entrada.ai` citation — vendor blog, not authoritative. Every retained
citation must resolve to `docs.databricks.com` or the Databricks blog.

## Acceptance criteria (backpressure)

`scripts/audit_check.py` must gate this skill exactly as it gates the other 31:

- frontmatter within all limits; `name` equals directory name
- body under 500 lines and under 5,000 tokens
- exactly two H2 headings, in order
- zero `../` anywhere in the skill
- both reference files linked from SKILL.md with a stated load condition
- full `references/` path prefix on both links
- neither reference file links to the other
- TOC in any reference over 100 lines
- description contains a when-clause and names both sibling products
- zero date literals anywhere in the skill

Plus: `python3 scripts/skills.py validate` exits 0, and `manifest.json`
regenerates cleanly with the skill present in all four marketplace catalogs
after `scripts/skills.py generate`.

## Out of scope

MCP-as-delivery (`deploy_mcp.py` patterns), Genie Agents curation, Genie One,
workspace instruction files. The instruction-file split — safety posture belongs
in `.assistant_workspace_instructions.md` because instructions apply to every
response while skills fire only on description match — is correct but is a
separate deliverable, not part of this repo.
