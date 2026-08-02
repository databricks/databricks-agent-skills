0a. Study `specs/*` with up to 250 parallel Sonnet subagents to learn the remediation rubric and the structural contract.
0b. Study @IMPLEMENTATION_PLAN.md.
0c. The corpus under audit is `skills/*` and `experimental/*` — markdown skill directories, not application source. There is no `src/`.

1. Your task is to remediate audit findings per the specs using parallel subagents. Follow @IMPLEMENTATION_PLAN.md and choose the most important item to address. Before making changes, search the corpus (do not assume a defect is present or already fixed) using Sonnet subagents. You may use up to 250 parallel Sonnet subagents for searches and reads, and only 1 Sonnet subagent for running backpressure. Use Opus subagents when a judgment call is needed (which orphan reference to delete versus link, how to word a replacement description).

2. After each change, run backpressure for the finding you addressed. The commands are in @AGENTS.md. Backpressure here is a count, not a feeling: `scripts/audit_check.py` reproduces the audit's exact per-finding numbers, so a finding is resolved when its count reaches zero and no other count regresses. Ultrathink.

3. When you discover issues, immediately update @IMPLEMENTATION_PLAN.md with your findings using a subagent. When resolved, update and remove the item.

4. When backpressure passes, update @IMPLEMENTATION_PLAN.md, then `git add -A`, then `git commit -s` with a message naming the finding ID and the skills touched. Sign-off is mandatory — upstream rejects unsigned and pseudonymous commits. After the commit, `git push`.

99999. Important: edits are surgical. Byte-preserve everything outside the named fix site. No reformatting of untouched sections, no opportunistic improvements, no scope creep. A diff that touches more than the finding requires is a failed increment even when backpressure passes.

999999. Important: never edit generated artifacts — `manifest.json`, `plugins/**`, the four `marketplace.json` catalogs, `rules/databricks-routing.mdc`, `hooks/*.json`, `agents/openai.yaml`, `assets/**`. Their source is `metaplugin/plugin.meta.json` and `scripts/skillsgen/`. If a change appears to require touching one, the fix belongs upstream of it; record that in @IMPLEMENTATION_PLAN.md and pick a different item.

9999999. Do not create git tags. Upstream release tagging runs off `metaplugin/version.meta.json`; tags created here would collide.

99999999. One finding class per branch. If the most important remaining item belongs to a different finding class than this branch's scope, stop and say so rather than widening the branch.

999999999. Keep @IMPLEMENTATION_PLAN.md current with learnings using a subagent — future loops depend on it to avoid redoing work. Update especially after finishing your turn, including the current count for every finding you touched.

9999999999. When you learn something new about how to run backpressure, update @AGENTS.md using a subagent, but keep it brief. If you ran a command more than once before finding the correct form, that belongs in AGENTS.md.

99999999999. For defects you notice that are outside the current branch's scope, document them in @IMPLEMENTATION_PLAN.md under "Deferred to other branches" using a subagent. Do not fix them here.

999999999999. Remediate completely. A partially-swept finding is worse than an untouched one, because the count no longer tells the truth about the corpus.

9999999999999. When @IMPLEMENTATION_PLAN.md becomes large, periodically clear completed items using a subagent.

99999999999999. If you find the specs in `specs/*` inconsistent with the corpus — a count that cannot be reproduced, a rule that contradicts another — use an Opus subagent with ultrathink to reconcile, and record the reconciliation in the spec file. Do not silently work around a spec.

999999999999999. IMPORTANT: keep @AGENTS.md operational only. Status and progress belong in @IMPLEMENTATION_PLAN.md. A bloated AGENTS.md pollutes every future loop's context.
