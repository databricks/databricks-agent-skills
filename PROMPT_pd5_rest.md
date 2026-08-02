Read PROMPT_build.md, AGENTS.md, and specs/02-audit-findings.md.

Branch scope: PD-5 across the 14 skills that still carry reference-to-reference
links. 137 links remain repo-wide. databricks-pipelines is already swept on this
branch's parent - do not touch it.

Order by volume, heaviest first. Get the per-skill breakdown from
python3 scripts/audit_check.py --only PD-5 --details

Also in scope on this branch: PD-5b, 12 files in
skills/databricks-apps/references/appkit/. Flatten to references/appkit-*.md and
relink from SKILL.md. It is the repo's only two-level reference directory and it
compounds the same defect.

Apply the method established on databricks-pipelines: each inter-reference link
becomes the target's plain name, basename minus .md, keeping any #anchor so the
pointer still names its section. Leave fenced code alone - the checker exempts it
under D1 and those paths are working examples. Every reference file must be
linked directly from SKILL.md with a stated condition for when to read it.

Watch for the substitution demoting a product name to a filename, as happened at
streaming-patterns.md:94. Read each substituted line in context before moving on.

Clearing PD-5 links may also clear PD-4c orphans, as it did on pipelines. That is
expected and correct - report it, do not avoid it.

Two-commit split per skill batch, as established: the content sweep first, then
the chore: self-heal bundle from source regeneration. GEN-1 and skills.py validate
cannot both pass in one commit.

Commit with git commit -s.

Emit the completion promise only when audit_check.py --only PD-5 exits 0 repo-wide,
PD-5b is zero, and no other finding count has increased. Run the full unscoped
audit_check.py before the final commit to confirm.
