0a. Study `specs/*` with up to 250 parallel Sonnet subagents to learn the remediation rubric and the structural contract.
0b. Study @IMPLEMENTATION_PLAN.md (if present) to understand the plan so far. It may be wrong.
0c. The corpus is `skills/*` (30 stable) and `experimental/*` (2). Markdown skill directories, not application source.

1. Use up to 250 Sonnet subagents to measure the corpus against `specs/*`. Run `python3 scripts/audit_check.py` first — if it exists, its output is the ground truth for every count. If it does not exist yet, that is the highest-priority item in the plan, because every other gate depends on it.

   Use an Opus subagent to analyze findings, prioritize, and create or update @IMPLEMENTATION_PLAN.md as a bullet list sorted by priority. Ultrathink.

   Priority order: findings whose count is currently non-zero and whose blast radius is largest. Within a finding class, the skill with the most occurrences first.

IMPORTANT: Plan only. Do NOT edit any file under `skills/` or `experimental/`. Do NOT commit corpus changes. Do NOT assume a defect exists — confirm by measurement first. The audit's headline counts are in `specs/02-audit-findings.md`; if your measurement disagrees with a stated count, the disagreement itself is the finding and goes in the plan.

Each plan item must carry:
  - the finding ID (SPEC-10, PD-5, DESC-1, ...)
  - the exact file path or paths
  - the current count and the target count (almost always zero)
  - the backpressure command that proves it resolved

ULTIMATE GOAL: `python3 scripts/audit_check.py` reports zero must-fix across all 32 skills, `python3 scripts/skills.py validate` exits 0, and the unittest suite passes — achieved through commits that are single-concern and cherry-pickable, because upstream cannot merge from this fork directly and every change has to survive migration through their internal repository as a discrete unit.

If a finding in `specs/02-audit-findings.md` turns out to be a policy question rather than a mechanical defect (a documented convention, a docs-side error, a maintainer decision), do not plan a fix. Move it under a "File as issue, do not PR" heading with a one-line rationale.
