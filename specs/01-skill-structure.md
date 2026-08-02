# Spec: skill structure contract

Derived only from three published sources. Sections of those pages not named
here are out of scope and must not influence remediation.

- Skill structure: `platform.claude.com/docs/en/agents-and-tools/agent-skills/overview#skill-structure`
- Progressive disclosure: `platform.claude.com/cookbook/skills-notebooks-01-skills-introduction#progressive-disclosure-architecture`
- Conceptual overview: `platform.claude.com/cookbook/skills-notebooks-01-skills-introduction#skills-conceptual-overview`

## Skeleton

```
---
name: your-skill-name
description: Brief description of what this Skill does and when to use it
---

# Your Skill Name

## Instructions
[Clear, step-by-step guidance for Claude to follow]

## Examples
[Concrete examples of using this Skill]
```

Applies as a target for newly authored skills. Existing skills are not
restructured wholesale — that is out of scope for this remediation.

## Frontmatter limits (hard)

| Field | Rule |
|---|---|
| `name` | required; 1–64 chars; `a-z0-9-` only; no leading, trailing, or doubled hyphen; must equal the directory name; must not contain `anthropic` or `claude` |
| `description` | required; 1–1024 chars; states both what the skill does and when to use it; no XML tags |
| `compatibility` | optional; ≤500 chars |
| `metadata` | optional; string→string map; the spec's designated extension point |
| `parent` | not in the spec, but documented in this repo's `CONTRIBUTING.md`. Leave in place. Policy question, not a defect. |

No XML tags in any frontmatter value.

## Progressive disclosure (three levels)

- **Level 1 — metadata.** `name` + `description`. Always resident. Sum across
  all installed skills is the repo's fixed context cost.
- **Level 2 — SKILL.md body.** Loads when the skill fires. Under **500 lines**
  and under **5,000 tokens**. Both bind independently: a skill can pass the
  line check and fail the token check when its lines are long.
- **Level 3 — `references/`.** Loads only when SKILL.md tells the agent to read
  it. Every reference file must be linked from SKILL.md with a stated condition
  for when to read it. A bare "see references/ for details" defeats the
  mechanism and counts as unrouted.

Token basis throughout: **characters ÷ 4**, body only, frontmatter excluded.

## Link rules

- Relative from the skill root, forward slashes, full `references/` prefix.
  A bare basename (`GOTCHAS.md`) is a defect even when the file resolves by
  luck.
- No `../` anywhere in a skill directory. Skills install as subsets; a path
  reaching into a sibling dangles.
- References are one level deep. A reference file linking to another reference
  file creates a second hop that partial reads (`head -100`) will miss.
- Reference files over 100 lines carry a table of contents.

## Description quality

The description is the only lever on auto-invocation. Body edits cannot fix a
trigger miss.

- States what the skill does **and** when to use it.
- Third person.
- Carries literal trigger phrasings a user would type.
- Where a sibling could plausibly claim the same request, carries a
  "do not use for" clause naming it.
- "Covers X, Y, Z" describes contents, not conditions. That is a defect.

Model to follow: `skills/databricks-data-discovery` (lists literal user
phrasings). Second-best: `skills/databricks-apps-python` (names its sibling and
the conditions under which it wins instead).
