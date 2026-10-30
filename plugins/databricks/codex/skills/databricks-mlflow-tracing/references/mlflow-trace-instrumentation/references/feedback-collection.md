# Feedback collection

Use when implementing authorized user ratings/comments tied to a concrete trace. Capture and persist the active trace ID with the application request ID (`mlflow.get_current_active_span().trace_id` in Python; `mlflow.getCurrentActiveSpan()?.traceId` in TypeScript), then return it or look it up when feedback arrives later. In the same Python process, `mlflow.get_last_active_trace_id()` can recover the most recently completed trace; across processes, use the persisted mapping or a bounded trace search on recorded request metadata. Do not confuse a trace ID with a run ID.

## Record the judgment and source

Check the installed SDK supports these public APIs:

```python
import mlflow
from mlflow.entities import AssessmentSource

mlflow.log_feedback(
    trace_id=trace_id, name="user_rating", value=rating,
    source=AssessmentSource(source_type="HUMAN", source_id=reviewer_id),
)
```

Use `logFeedback` only when the installed `@mlflow/core` exports it. Published version 0.4.0 does not; send the trace ID, rating and reviewer identity to the application's feedback endpoint and record it with a supported server-side MLflow client. Do not invent `mlflow.logFeedback` on 0.4.0.

Values may be numeric ratings, text comments or boolean judgments. Preserve actual source identity and meaning: HUMAN for user/manual review, LLM_JUDGE for automated model judgments, CODE for programmatic checks. Do not label generated feedback as human. A zero/false value is not a logging failure; a scorer error is not a negative judgment.

Expected-output labels are expectations, not feedback judgments. For requested scorer alignment or Review App labeling use `databricks-mlflow-evaluation`. For feedback field/source compatibility use the [entity API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.entities.html) and the installed SDK APIs. Verify the stored assessment belongs to the intended trace and retains value/source; recording user complaints during diagnosis still requires authorization.
