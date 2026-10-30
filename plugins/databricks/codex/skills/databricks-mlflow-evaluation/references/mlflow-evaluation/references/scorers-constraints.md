# Scorer compatibility and missing-score checks

Read when implementing custom scorers/judges or diagnosing lost metrics. Inspect the installed API and [GenAI
API documentation](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.genai.html) because accepted
templates, types, constructors, and aggregations vary by release. If docs are unavailable, verify with
installed introspection and a small call; stop if correctness remains uncertain.

## Judge templates

`make_judge` instructions need at least one supported template variable, not an unbound `{query}` placeholder.
For final-output criteria use `{{ inputs }}` / `{{ outputs }}` and optional `{{ expectations }}`. `{{ trace
}}` must stand alone rather than being mixed with other variables; it already includes execution inputs and
outputs. Verify the separate `{{ conversation }}` contract for session judges.

For a single evidence span, select it deterministically in a `@scorer` using `trace.search_spans()` and pass
the selected evidence/claim to the judge; reserve whole-trace templates for whole-execution criteria.

CLI flags are version-sensitive: inspect `mlflow scorers register-llm-judge --help` (commonly `-n` name, `-i`
instructions, `-d` description). One compatible shape is:

```bash
uv run mlflow scorers register-llm-judge -n ToolUsage \
  -i "Examine {{ trace }}. Did the agent use appropriate tools? Return 'yes' or 'no'."
```

## Stored assessments are not necessarily aggregate scores

| Value | Aggregation contract |
| --- | --- |
| `True`, `False` | Valid, usually 1 / 0; False is a real negative result |
| Numeric values, including `0` / `0.0` | Valid within the agreed scale |
| `"yes"`, `"no"` | Supported binary string values |
| `"pass"`, `"fail"`, `"passed"`, `"failed"`, `"correct"`, `"not_applicable"`, string `"true"` / `"false"` | Can be stored but cast to None and omitted from aggregate metrics |
| String `"1"` / `"0"` | Do not rely on numeric-string coercion |
| `None`, skipped assessment, or assessment error | Not successful scoring; expose missing/error counts |

Inspect actual row values and `results.metrics`, not just run existence or trace OK status. Never test score
validity with truthiness: zero/False must survive. Uniform negatives warrant investigation, not automatic
rejection. Do not change the criterion to manufacture a nonzero score.

Prefer bool or `Literal["yes", "no"]` for binary judge output; numerics require a meaningful scale. For
not-applicable cases, explicitly skip and report coverage or return `Feedback(value=True, rationale="not
applicable: ...")` under the agreed rubric. A categorical alignment label can be valid feedback without being
a numeric optimization objective: verify conversion separately.

## Custom feedback and registration

- Decorate code checks with `from mlflow.genai.scorers import scorer`.
- Return supported primitives, `Feedback(value=..., rationale=...)`, or a supported list of Feedback objects,
  not arbitrary dicts/tuples. Multiple Feedback values need distinct names to avoid overwrites.
- Put explanations in rationale. Malformed/missing required inputs should not silently pass.
- Verify constructors rather than assuming historical requirements (for example `Guidelines` name/default
  behavior). Guidelines require inputs and outputs; their prose is a requirement, not a custom Jinja-variable
  binding scheme.
- Check supported aggregation names in the installed release. Historical supported names include `min`, `max`,
  `mean`, `median`, `variance`, `p90`; do not assume `p50`, `p99`, or `sum` are accepted.
- Check scorer serialization in the actual monitoring environment, including dependency imports and
  annotations. Function-local imports may help serialization but cannot install missing dependencies; see
  [online monitoring](databricks-online-monitoring.md).
- Verify `required_columns` plus semantic prerequisites: `Correctness` needs expectations and retrieval
  scorers need RETRIEVER spans, not TOOL-only traces.

Re-register changed definitions only after the small check confirms valid outputs and expected verdicts.
Preserve the old version for reproducibility.
