Read PROMPT_build.md, AGENTS.md, and every file under specs/.

Close out Phase 1. Seven finding classes remain, all mechanical. Work them one
class per branch, in this order, branching each from the previous so counts stay
comparable:

1. ralph/spec-10b-basenames  SPEC-10b, 64 mentions across 2 skills.
   databricks-mlflow-evaluation 61, databricks-app-design 3. Prefix each with
   its full references/ path. Byte-preserve the rest of mlflow-evaluation's
   SKILL.md - its four numbered workflow tables are the best routing in the repo
   and only the paths are wrong.

2. ralph/spec-10a-remainder  SPEC-10a-intra, 19 links.

3. ralph/pd-4-routing  PD-4a, 3 pointers to nonexistent skills. In
   databricks-docs, also settle the DLT / Lakeflow terminology mixing in the same
   pass. Leave PD-4b alone - it is blocked and belongs in an issue.

4. ralph/new-c-root-refs  NEW-C, 4 reference files at skill root.
   databricks-core has three, experimental/databricks-ai-runtime one. Move into
   references/ and update every inbound link.

5. ralph/desc-1-triggers  DESC-1, 6 descriptions with no trigger conditions.
   Target 300-500 chars, hard cap 1024, third person. Model on
   databricks-data-discovery, which lists literal user phrasings. Add a
   do-not-use-for clause where a sibling could claim the same request. Report the
   resident-set delta against the 2975-token stable baseline.

6. ralph/pd-1-ceilings  PD-1 and PD-2, 3 skills each, 4 unique. Move content
   verbatim, never summarise. Leave routing pointers with load conditions. Total
   characters per skill directory must land within 2 percent of pre-split, which
   proves content moved rather than vanished. Measure that parity on the split
   commit alone, before any TOC commit adds characters.

7. ralph/pd-6-toc  PD-6, the largest and most mechanical class. The audit count
   of 125 files across 26 skills predates branches 4 and 6 - re-measure with
   audit_check.py --only PD-6 --details at branch start and work the current
   population. Start with databricks-metric-views references
   metric-view-advisor, the largest file in the repo. A table of contents is
   derivable from the headings already present.

Rules that apply to every branch:

A reference file that this branch creates or relocates ships with a table of
contents as part of authoring it. That is not a PD-6 fix and not scope creep -
it is finishing the file you just wrote or moved. Expect PD-6 to rise on
branches 4 and 6 by exactly the count of files those branches added to the
references population, and to fall by the same amount once those TOCs land.
Report both numbers. Any PD-6 movement not attributable to files the branch
itself created or moved is a regression and must be investigated.

Any branch that creates, moves, or deletes a file under skills/ or
experimental/ runs scripts/skills.py generate and git adds the regenerated
artifacts in the same commit. Green validate in the working tree is not green at
the commit, and CI only sees the commit.

Link substitution can demote a product name to a filename. Before moving on from
any substituted line, read it in context and check whether the label named the
file or named a thing. Ten of these were caught by reading diffs on the PD-5
sweeps and no gate sees this class.

Clearing one finding may clear another as a side effect, as PD-5 cleared PD-4c.
That is correct - report it, do not avoid it. Never fix a finding outside the
branch scope on purpose; record it under Deferred to other branches.

Gate each branch with audit_check.py --only ID --details and use the exit status,
not a grep of stdout. Run the full unscoped audit_check.py before the final
commit of each branch to confirm no other row increased, applying the PD-6
attribution rule above.

Commit with git commit -s, one concern per commit. Push each branch when its
gate is green.

Update IMPLEMENTATION_PLAN.md as each class closes.

Emit the completion promise only when SPEC-10b, SPEC-10a-intra, PD-4a, NEW-C,
DESC-1, PD-1, PD-2 and PD-6 are all zero, the three blocked rows are unchanged at
19 / 21 / 7, no other row increased, skills.py validate exits 0, and the unittest
suite passes.
