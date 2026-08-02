Read PROMPT_build.md, AGENTS.md, and specs/02-audit-findings.md.

Three hardening tasks from the PD-5 sweeps. Edit no file under skills/ or
experimental/.

1. GEN-1 currently fails on any change under plugins/, manifest.json, rules/, or
hooks/. That is structurally incompatible with skills.py validate, which fails
when they are stale, so every sweep pays a two-commit tax. Rewrite GEN-1 to pass
when the working tree matches what scripts/skills.py generate would produce, and
fail only when it does not. Legitimate regeneration passes; hand-mirroring still
fails. Verify against the four self-heal commits on ralph/pd-5-rest.

2. AGENTS.md is missing two facts that cost real time. Add, briefly: manifest.json
is generated alongside plugins/ and must be staged with it - validate passing in
the working tree does not mean it passes at the commit, because generate writes
the file but only git add makes it true for CI. And: when substituting a link for
a plain name, check whether the label named the file or named a thing. Ten
product-name demotions were caught by reading diffs, not by any gate.

3. specs/02-audit-findings.md still lists PD-4c as a separate finding. All three
orphans cleared inside the PD-5 sweeps because a reference reachable only through
a second hop is an orphan whether or not the orphan checker noticed. Record that
PD-4c is a consequence of PD-5, not an independent class, and that
ralph/pd-4c-orphans is retired.

Two-commit split per the established workflow if plugins/ changes.
Commit with git commit -s.

Emit the completion promise when audit_check.py runs clean on a regeneration
commit without a GEN-1 violation, the unittest suite passes, and both doc edits
are in.
