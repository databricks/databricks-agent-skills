# Run and register an agreed scorer suite

Criterion design belongs to the [bundled evaluation guide](../guide.md); this reference covers model configuration, registration, reuse,
and execution. Check the [GenAI
API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.genai.html) and installed signatures for
version-sensitive details. If docs are unavailable, introspect the installed API and stop any operation whose
contract remains unclear.

## Check data and model before registration

Inspect installed built-ins (`mlflow scorers list -b`, `get_all_scorers()`, and module exports) and each
selected scorer's `required_columns`. Constructor-argument scorers may not appear in `get_all_scorers()`.
Check actual trace structure and ground truth: retrieval scorers require RETRIEVER spans; `Correctness` needs
expected facts/response. Match session scorers to session data.

### Model selection for scorers

Deterministic scorers require no judge model or provider credentials. For model-backed scorers:

1. Preserve the approved suite's explicit model and the project's `MLFLOW_GENAI_JUDGE_DEFAULT_MODEL` /
   existing scorer configuration. Never silently replace it with a remembered model ID.
2. If no model is selected, identify an available suitable model and configure it explicitly. The agent's
   working provider can avoid new credentials, but it is not necessarily the right judge; check quality and
   cost.
3. Verify the effective model with a small real scorer call. Credentials present in the environment and a
   trace marked OK do not prove a judge call succeeded.

| MLflow model URI | Access |
| --- | --- |
| `databricks` | Managed Databricks judge on supported Databricks tracking setups |
| `databricks:/<endpoint>` | Intended Databricks serving endpoint |
| `openai:/<model>` | Configured OpenAI credentials / gateway |
| `anthropic:/<model>` | Configured Anthropic credentials / gateway |
| `gemini:/<model>` | Configured Gemini credentials (`GEMINI_API_KEY` or supported `GOOGLE_API_KEY`) |

Use `:/`, not `:` or LiteLLM's slash-only model syntax. Defaults depend on MLflow version/backend
(historically Databricks managed judging on Databricks and OpenAI elsewhere); inspect them rather than
assuming no new provider is needed. Preserve gateway base URL and project authentication. A model-access
failure is a blocker, not authorization to change providers.

## Register and retrieve

List the intended experiment's registered scorers first:

```bash
uv run mlflow scorers list -x "$MLFLOW_EXPERIMENT_ID"
```

Use existing scorers and add only missing agreed definitions. Register both built-ins and custom scorers, then
list them again to verify persistence. Load the registered suite with the installed `mlflow.genai.scorers`
retrieval API; inspect its experiment/name/version parameters rather than rebuilding equivalent inline
definitions.

Example registration, after selecting a resolvable `JUDGE_MODEL` and the intended experiment:

```python
import os
from typing import Literal
from mlflow.genai.judges import make_judge

judge = make_judge(
    name="ToolUsageAppropriate",
    instructions=(
        "Examine {{ trace }}. The agent should use the appropriate available tools "
        "when needed for the user's request, and avoid unnecessary calls. "
        "Return 'yes' if it does, otherwise 'no'."
    ),
    feedback_value_type=Literal["yes", "no"],
    model=os.environ["JUDGE_MODEL"],
)
registered = judge.register()
```

For CLI registration, inspect `mlflow scorers register-llm-judge --help` before using flags. Do not fall back
to undocumented legacy `--variables` / `--output pass/fail` recipes. Python registration can expose clearer
errors. Both paths must satisfy [scorer constraints](scorers-constraints.md).

Preserve definition/model/version provenance. A changed criterion or aligned judge needs a distinguishable
version; do not mix its scores with an earlier judge's scores in an agent before/after comparison.

## Verify assessments before a full run

Test representative known-good and known-bad cases, including required-tool and no-tool cases when
appropriate. A single-trace check can use:

```bash
uv run mlflow traces evaluate --scorers ToolUsageAppropriate \
  --trace-ids "$TRACE_ID" --output json > scores.json 2> scorer.log
```

Inspect row-level assessment values, rationale, errors, and aggregate inclusion. A genuine zero/False/"no" is
valid; missing, skipped, error-only, and non-aggregating values must not masquerade as successful scoring.
Review disagreements against the actual criterion rather than loosening it to raise scores.

For human disagreement use the [alignment
reference](judge-alignment.md). For production scoring read
[Databricks online monitoring](databricks-online-monitoring.md): registration does not start monitoring, and
serialization/sample settings need separate verification.
