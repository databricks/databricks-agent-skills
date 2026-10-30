# Root span previews and compact values

Use only when root I/O is not already readable. MLflow automatically handles chat-shaped `messages`, `choices[0].message`, and Responses-API `input` lists; do not override useful automatic previews. The UI truncates display, so do not add arbitrary string slicing.

## Set clean inputs/outputs preview for trace list UI

Inside the traced application function, change display without replacing stored span data:

```python
mlflow.update_current_trace(
    request_preview=f"customer={customer}, date={date}",
    response_preview=state.get("note_text") or "",
)
```

## Override span inputs and outputs with compact values

Only when deliberately reducing stored root state, use explicit setters. They take precedence over decorator capture; the function can still return the full state. Preserve useful debugging evidence and document any omitted content.

```python
@mlflow.trace(span_type=SpanType.AGENT)
def run_agent(graph, customer, date):
    span = mlflow.get_current_active_span()
    span.set_inputs({"customer": customer, "date": date})
    state = graph.invoke({"customer": customer, "date": date})
    span.set_outputs({"output_path": state.get("output_path"),
                      "note_text": state.get("note_text")})
    return state
```

The example assumes `import mlflow` and `from mlflow.entities import SpanType`. This outer boundary is optional application work, not a reason to wrap each autologged graph node.
