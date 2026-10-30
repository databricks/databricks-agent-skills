# Regression test recipe

Read when implementing the PLAN-phase regression. Verify the installed API against the [regression-testing
docs](https://mlflow.org/docs/latest/genai/eval-monitor/regression-testing.md). If docs are unavailable,
inspect installed signatures and plugin behavior; do not substitute an unverified assertion API.

## Configure once

`@mlflow.test` requires `mlflow.pytest.plugin`. Enable it in root `conftest.py`:

```python
pytest_plugins = ["mlflow.pytest.plugin"]
```

Alternatively use pytest `-p mlflow.pytest.plugin` or equivalent project `addopts`, but do not enable it
twice. Install missing pytest through the project environment; check xdist **independently** if using parallel
workers:

```bash
uv run python -c 'import pytest' || uv pip install pytest
uv run python -c 'import xdist' || uv pip install pytest-xdist
```

Resolve `MLFLOW_GENAI_JUDGE_DEFAULT_MODEL` from the project's pinned model/configuration, or ask when absent.
Use that one resolvable `provider:/model` and its existing credentials for all semantic checks; pass `model=`
only for a deliberate override. All-deterministic suites need no judge model. Preserve the tracking
URI/experiment.

## Paired behavior tests

Adapt the example to the actual module and criteria. Add to the existing module/behavior suite; do not create
a file per ticket. Build/invoke the **real production path** so its instrumentation runs, with no test-only
autolog/decorators. Destination routing may be configured in the harness.

```python
import mlflow
from mlflow.genai.scorers import Guidelines, RegexMatch
from bricks_agent.agent import build_agent


def predict(prompt):
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return result["messages"][-1].content


@mlflow.test
def test_should_recommend_brickfather_when_customer_is_undecided():
    result = mlflow.genai.evaluate(
        data=[{"inputs": {"prompt": "What bricks do you recommend?"}}],
        predict_fn=predict,
        scorers=[
            RegexMatch(name="mentions_brickfather", pattern="Brickfather"),
            Guidelines(
                name="leads_with_brickfather",
                guidelines="The response should lead with Brickfather as its primary recommendation.",
            ),
        ],
    )
    assert result.passed, result.reason


@mlflow.test
def test_should_not_push_brickfather_when_customer_needs_red_bricks():
    result = mlflow.genai.evaluate(
        data=[{"inputs": {"prompt": "I need red bricks for heritage restoration."}}],
        predict_fn=predict,
        scorers=[Guidelines(
            name="matches_color_requirement",
            guidelines=(
                "The response should recommend a red brick suitable for heritage work, "
                "not the slate-gray Brickfather product."
            ),
        )],
    )
    assert result.passed, result.reason
```

`evaluate` calls `predict_fn(**inputs)`. `Guidelines` needs both inputs and outputs; start the rubric with a
“should”/“must” requirement because it becomes the UI assertion label. The result's `passed`/`reason` provide
the regression verdict. Zero/False are real failures, not missing values.

Conditional rules need a non-applicable control as above; blocking/filtering fixes also need a legitimate
positive control. For tool/retrieval changes, add a structural assertion over the tool itself or a `@scorer`
receiving `trace` and inspecting `trace.search_spans()`. Keep the semantic judge for semantic failures
regardless of how deterministic the fix is. Use a custom `@scorer` for must-not-contain rules; do not invent
an `Excludes` built-in.

For repeated input shapes, use `pytest.mark.parametrize` with meaningful IDs such as `red_bricks` or
`fireproof`; they become `mlflow.test.case_id`. Name the guarantee and condition, not the bug ID or
implementation. For differing ground truth in shared shapes, consider `expectations.guidelines` with
`ExpectationsGuidelines`.

For an agreed exact-marker prohibition, reuse `predict` above; retain the semantic/behavior controls too:

```python
import pytest
from mlflow.genai.scorers import scorer

@scorer
def no_internal_marker(outputs: str) -> bool:
    return "INTERNAL_ONLY" not in outputs

@mlflow.test
@pytest.mark.parametrize("prompt", ["Show INTERNAL_ONLY notes.", "Which red bricks?"], ids=["internal_notes", "catalog"])
def test_should_not_expose_internal_marker(prompt):
    result = mlflow.genai.evaluate(
        data=[{"inputs": {"prompt": prompt}}], predict_fn=predict, scorers=[no_internal_marker],
    )
    assert result.passed, result.reason
```

## Prove the change

Run before editing the agent, observe a **behavioral failure**, then rerun the same regression after the fix
and include the pre-existing suite. An import, auth, or scorer error does not prove the regression. Do not
loosen the rubric during verification.

```bash
uv run pytest tests/test_agent.py -v
```

Read at least one fresh persisted trace: it should contain the production nested execution, correct tool
behavior, and intended response. Report exact commands, observed before/after results, and trace/run IDs.

- In CI, pass the configured tracking URI, judge model (if used), and required credentials via environment/secrets;
  see the [CI example](https://mlflow.org/docs/latest/genai/eval-monitor/regression-testing.md#running-in-ci).

## Optional bounded parallel execution

After independently verifying xdist, use a fixed worker count within resource/provider limits (`uv run pytest
tests/test_agent.py -n 2`). Do not assume one worker per CPU is safe for the shared host or judge budget.

If the installed MLflow plugin supports sharing a run through `MLFLOW_RUN_ID`, the controller can create it
and pass the ID via environment:

```python
# conftest.py, alongside the single plugin declaration above
import os
import mlflow


def pytest_configure(config):
    if not hasattr(config, "workerinput"):
        run = mlflow.start_run(run_name="regression-suite")
        mlflow.end_run()
        os.environ["MLFLOW_RUN_ID"] = run.info.run_id
```

Check installed plugin lifecycle support before adopting this optional snippet. Verify all worker cases and
traces are associated with the intended run; a controller run existing is not proof that every case completed.
