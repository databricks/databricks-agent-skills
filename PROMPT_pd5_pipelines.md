Read PROMPT_build.md, AGENTS.md, and specs/02-audit-findings.md.

Branch scope: PD-5 in skills/databricks-pipelines ONLY. 91 reference-to-reference
links across its reference files. Touch no other skill.

Strip inter-reference links to plain names. Every reference file must be linked
directly from SKILL.md with a stated condition for when to read it. A bare
"see references/ for details" does not satisfy this.

Do not touch generated artifacts. The GEN-1 guard will catch it.

Backpressure: python3 scripts/audit_check.py --only PD-5
Also run scripts/skills.py validate and the unittest suite before each commit.

Commit with git commit -s, one concern.

Emit the completion promise only when audit_check.py reports zero PD-5 links
and zero orphans for databricks-pipelines, and no other finding count has
increased.
