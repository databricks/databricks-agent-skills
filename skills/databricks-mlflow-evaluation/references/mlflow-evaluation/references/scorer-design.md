# Build a scorer

Use this reference to choose what to measure, implement scorers, or align judges. A first judge is a draft until checked against human standards.

Reuse the app purpose, known failures, success criteria, available evidence, existing labels, and configured
model. Ask at most three opening questions before showing a draft: what the app does, its worst failure, and
what it should do when unsure. Do not interview the user about internal schemas or state machines. Translate
vague goals into proposed observable criteria for correction.

For domain-expert workflows, preserve the expert criterion and labels as the source of truth; align against
matching labels and validate on a separate holdout using [judge alignment](judge-alignment.md).

If criteria, implementation choices, edge verdicts, and outputs are already confirmed, implement them without
reconfirmation. Traces are optional unless the criterion requires execution internals; inputs plus outputs or
a `predict_fn` can support a prototype.

## Step 1: Draft atomic criteria and establish observability

Use 3–5 recurring, high-signal checks. Adding one requires replacing a weaker check. One criterion per scorer:
split bundled requirements and avoid an “overall quality” judge.

Include both rule checks and at least one **user outcome** check: did the user get what they came for? Text
presence or a policy flag alone is not an outcome. If success is unclear, propose a concrete outcome for the
user to correct. Keep outcome criteria atomic too.

Example outcome: **an eligible order was actually cancelled**, verified by tool result or post-action lookup:

| Evidence for an eligible order | Outcome verdict |
| --- | --- |
| Assistant says "Cancelled"; order state remains `open` | `False` |
| Order state becomes `cancelled` for the requested order ID | `True` |
| No authoritative state is available | Unscorable; report missing evidence, not success |

Inspect one or two existing traces or records to confirm inputs, outputs, expectations, span types, and
single-turn versus session scope. Map each criterion to the stage where its evidence appears; do not judge
only the final response when the failure occurred upstream.

## Step 2: Choose the cheapest reliable implementation

Inspect the installed catalog before choosing a custom judge:

```python
from mlflow.genai.scorers import get_all_scorers
import mlflow.genai.scorers as scorers
for check in get_all_scorers():
    print(type(check).__name__, check.required_columns,
          getattr(check, "is_session_level_scorer", False))
print([name for name in dir(scorers) if name[0].isupper()])
```

`get_all_scorers()` covers default-instantiable built-ins; constructor-argument checks such as `Guidelines`,
`RegexMatch`, and `ResponseLength` may appear only in exports. Verify their signatures and exact data
contracts. If MLflow is unavailable, continue criteria design but identify unverified names/contracts
explicitly.

Built-ins in MLflow 3.17.1; verify installed availability and contracts:

This table is representative, not complete. For the full current list, use the installed-catalog introspection
above and the [MLflow scorer documentation](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/).

| Built-in | Checks / evidence needed |
| --- | --- |
| `RelevanceToQuery` | Response addresses the input; inputs + outputs |
| `Correctness` | Expected facts/response are supported; inputs + outputs + ground truth in expectations |
| `Guidelines` | User's explicit policy; constructor `guidelines` + inputs + outputs |
| `RetrievalGroundedness` | Response grounded in retrieved content; inputs + trace with RETRIEVER spans and response |

| Criterion | First suitable implementation |
| --- | --- |
| JSON shape, exact values, fields, phrases, regex, length, expected tool calls, span latency | Deterministic `@scorer` or installed deterministic built-in |
| Standard relevance, correctness, safety, policy, tool/retrieval quality, conversation quality | Built-in with matching required data; consider `Guidelines` for the user's policy |
| Domain standard not covered by code or a built-in | `make_judge`; explain why both cheaper choices fail |

Use deterministic prefilters only where they reliably identify bright-line cases; judge ambiguous semantics. A
regex cannot establish tone, and a phrase check cannot cover paraphrases. A class-based scorer is warranted
only for reusable state/configuration.

Important data boundaries:

- `Correctness` needs expected facts/response; inspect `required_columns` and the actual ground truth, not
  just column names.
- `RetrievalGroundedness`, `RetrievalRelevance`, and `RetrievalSufficiency` require **RETRIEVER spans**;
  TOOL-only lookups do not qualify.
- For grounding in one tool result, use a `@scorer` receiving `trace`, select evidence with
  `trace.search_spans()`, and pass that evidence and the claim to a judge. Use `{{ trace }}` only for
  whole-execution criteria, such as sequencing/retries; do not mix it with other template variables.
- Session built-ins such as `UserFrustration`, `ConversationCompleteness`, and `KnowledgeRetention` have their
  own session contract. They cannot currently be aligned (`NotImplementedError`); if their standard is
  contested, use an alignable custom criterion. Single-turn built-in judges can support `align()`.

## Step 3: Sharpen and confirm only unresolved criteria

Propose pass/fail verdicts for a near miss, legitimate exception, severity boundary, and not-applicable case.
Have the domain expert correct or confirm at least one verdict per new criterion. Two people should be able to
label the same example consistently.

Present one table: **name | criterion | rule/outcome | implementation | why not cheaper | output | data
needed**. For every custom LLM judge, name both the rejected code check and built-in and why they are
insufficient. For cheaper checks, mark the rationale as already using the cheapest suitable option.

Wait for confirmation when these choices are new; an already approved suite is sufficient authorization. If
the user asks to discuss, keep full implementation until after agreement.

## Step 4: Implement the agreed suite

Use native built-ins, `from mlflow.genai.scorers import scorer`, or `from mlflow.genai.judges import
make_judge`. Deliver runnable imports, malformed-input guards, actual criterion-specific instructions, and a
native `mlflow.genai.evaluate(...)` example. `predict_fn` receives `**record["inputs"]`; precomputed outputs
need no predictor.

- Prefer boolean outputs; `"yes"`/`"no"` and numerics also aggregate. **`False` and zero are valid scores.**
  Strings such as `"pass"`, `"fail"`, `"correct"`, and `"not_applicable"` can disappear from metrics. Put
  explanations in `Feedback.rationale`, not its value. Use calibrated numeric scales only when justified.
- For not-applicable rows, use `Feedback(value=True, rationale="not applicable: ...")` or explicitly skip and
  report coverage; never silently count skipped rows as successful evaluations.
- Judge instructions need supported template variables (`{{ inputs }}`, `{{ outputs }}`, optional `{{
  expectations }}`, or exclusive `{{ trace }}` / session `{{ conversation }}` as supported by the installed
  API).
- Preserve the user's/project's configured judge model exactly. Otherwise choose an available explicit
  `provider:/model` at a suitable mid-tier; confirm access before relying on it. Do not introduce a provider
  implicitly. Skip model setup for deterministic suites. Scale up when clear labels expose disagreement, down
  only after measuring agreement; do not downgrade red-line checks merely for cost.
- State model-call cost at the user's volume. Built-ins supply tested scaffolding, not proof that their
  standard fits the product.

## Verification

Check implementation and data contracts, and supply known-pass, known-fail, malformed-input, and
applicable/not-applicable examples. Define how the caller should backtest; **do not run a full evaluation
campaign as part of scorer design**. Hand registration, dataset discovery, dry run, evaluation, and result
analysis to the [bundled evaluation guide](../guide.md), with the suite and its validation cases. Identify trace-only
upgrades separately; use the [bundled tracing guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-instrumentation/guide.md) for actual instrumentation gaps.

Before proposing new hand-labeling, look for existing complaints, incidents, support tickets, thumbs-down
feedback, refunds, or escalations. For every LLM judge, identify its alignment labels and separate held-out
validation. Subjective tone/style alignment can overfit. Preserve the base judge until held-out agreement
improves.

## References

- **Human labels, Review App labeling sessions, judge disagreement, or MemAlign:** read
  [judge-alignment.md](judge-alignment.md). Alignment requests may execute the approved alignment
  workflow; the design-only handoff does not prohibit this. The reference is local to this skill. Reuse
  matching human/judge assessment names and a separate holdout; verify successful assessments, explicit
  embedding/reflection models, and installed optimizer support. Missing optimizer/model prerequisites must be
  reported without claiming alignment succeeded. If an evaluation sibling is absent, perform only the
  authorized native registration, label discovery/pairing, or alignment operations using installed APIs and
  the linked official docs; no sibling installation is required.
- Registration/model URI details: [evaluation scorer reference](scorers.md),
  when installed.
- Custom feedback/template/aggregation errors: [scorer
  constraints](scorers-constraints.md), when installed; the essential contracts
  above also support standalone installation.

Use the exact [judge
alignment](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/alignment.md),
[MemAlign](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/memalign.md), or [GenAI
API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.genai.html) page for needed details,
checking installed signatures/version. Use [llms.txt](https://mlflow.org/docs/latest/llms.txt) only if a page
moved or is missing. If docs/sibling references are unavailable, use the local contract and introspection;
stop the affected operation if correctness cannot be established.
