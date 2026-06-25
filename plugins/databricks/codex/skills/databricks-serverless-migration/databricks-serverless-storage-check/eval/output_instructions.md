# Output Evaluation Criteria — databricks-serverless-storage-check

L5 grades the WITH-skill response against these expectations (plus per-case `expected_facts` / `assertions` in `ground_truth.yaml`). The goal of this rubric is to distinguish a real, scoped use of the storage-check skill from a generic "anything about serverless" reply.

## Expected Artifacts

Every WITH-skill response on a real storage-check trigger should produce:

- A diagnosis that names the antipattern explicitly (cross-task local-disk handoff) by symptom or pattern ID (`FANOUT001`–`FANOUT006`, `ENV001`)
- A recommended fix tier from the priority ladder: **UC Volumes → /Workspace → taskValues → keep local for intra-task only**
- A concrete code snippet (Python or DAB YAML) showing the before/after rewrite — not just prose
- The severity of the finding (Blocker / Warning / Info) so the user can decide whether to deploy
- Where appropriate, an invocation of `scripts/preflight.py` (or the explicit reason it was skipped, e.g. paste-only error trace)

## Mandatory Facts

Defined per test case in `ground_truth.yaml::test_cases[].expectations.expected_facts`. Common cross-case mandatory tokens:

- `/Volumes/` — the preferred handoff target. Should appear in every fix recommendation except taskValues-only cases.
- `cross-task` or `fan-out` — the antipattern label. Without one of these phrases the diagnosis is ambiguous.
- `taskValues` — when the payload is small (well under 48 KB), this must surface as the preferred fix over a file handoff.

## Negative Signals (the agent should NOT do these)

These are skill-specific anti-patterns that distinguish a misuse of the skill from a correct invocation:

- Recommend `chmod` / file ACL changes — that misdiagnoses the failure as a permission issue when it is actually a cross-node visibility issue.
- Tell the user to switch back to classic compute — the skill exists to keep them on serverless; rolling back is not the fix.
- Recommend UC Volumes for genuinely intra-task scratch (`/local_disk0/tmp` is correct there, and the parent migration skill explicitly recommends it). Misfiring the antipattern on a non-handoff scratch path is a regression.
- Generate code fixes for `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` — that is the `ENV001` info-only finding. Route to support escalation instead.
- Recommend writing to DBFS as the cross-task handoff target — DBFS mounts are deprecated and not the documented fix.
- Block deploy entirely with no actionable remediation — the skill must always end with at least one fix snippet the user can apply.

## Comparison Approach

The semantic grader handles the WITH vs WITHOUT comparison. Reference fixture remediation snippets live in `eval/source_of_truth/` (empty by default — drop in expected DAB rewrites for higher-fidelity L5 grading once a baseline exists).

## Skill Invocation Verification

For the user's stated goal of "verify the skill is correctly invoked":

- **L4** inspects whether the agent loaded the storage-check `SKILL.md` for cases 1–3 and did NOT misfire on case 4 (boundary). The four cases collectively exercise positive triggers (error symptom, fan-out, small-payload) and a negative boundary (single-notebook intra-task).
- **L5** WITH/WITHOUT compares answers: case 4's NEEDS_SKILL count should be near zero (correct scoping — the skill should not "add value" when not needed); cases 1–3's POSITIVE count should be high (skill provides real diagnostic lift over a baseline agent).
- A correctly integrated skill should also reference the parent (`databricks-serverless-migration`) when the user's workload is unmigrated, demonstrating the hierarchy works as intended.

## Severity Calibration Reference

When L5 classifies an assertion, use this hierarchy:

- POSITIVE — the WITH response named the pattern, surfaced the severity, and produced a runnable fix snippet
- NEEDS_SKILL — the WITHOUT response missed the diagnosis but WITH caught it (this is the lift the skill is paying for)
- REGRESSION — the WITHOUT response was better than WITH (skill made things worse — investigate)
- NEUTRAL — both responses arrived at substantively the same fix (skill is dead weight for this case)

## Per-Case Acceptance Bar

Each test case in `ground_truth.yaml` maps to a concrete acceptance bar that L5 should hold the WITH-skill response to:

- **Case 1 (trustedTemp permission denied)**: Must produce a UC Volumes fix snippet AND explain the per-node visibility issue. A reply that only mentions "use Volumes" without explaining why local disk fails is incomplete.
- **Case 2 (fan-out preflight)**: Must produce an explicit deploy decision (block / allow with changes / allow as-is) backed by the scanner's severity tier. Generic "looks risky" without a verdict is incomplete.
- **Case 3 (small payload)**: Must recommend `taskValues` as the primary fix and explain the 48 KB ceiling. Recommending Volumes for a 2 KB JSON payload is over-engineering and should be flagged as a partial regression.
- **Case 4 (single-notebook boundary)**: Must NOT recommend moving `/local_disk0/tmp` for intra-task scratch. Doing so is a false positive — the antipattern is cross-task, not intra-task, and confusing the two is the most common skill misuse.

## Cross-Reference With Pattern Catalog

The agent's response should cross-reference the in-skill pattern catalog (`references/pattern-catalog.md`) when discussing fixes. A response that quotes the catalog by pattern ID demonstrates the skill is loaded and applied; a response that produces correct fixes but never names a pattern ID is providing the right answer for the wrong reasons and should score lower on attribution.
