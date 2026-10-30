# Align a judge with domain-expert feedback

Use this when an LLM judge disagrees with domain experts or the user wants judge scores grounded in their own standards. `align()` improves the judge; it does not change the agent. A judge can be aligned without prompt optimization.

## Gather paired evidence

1. Define one criterion and a base `make_judge` with a clear feedback type and name. Use the [bundled evaluation guide](../guide.md) to register it to the experiment so the same judge can be retrieved later. A boolean, numeric, or categorical criterion can be aligned; keep its feedback type consistent with the human label schema.
2. Run the base judge on representative traces. Check both that the agent completed and that the judge produced a valid assessment; `trace.state == OK` alone does **not** prove the judge scored successfully. Tag eligible trace IDs for review and retain the originating evaluation run.
3. Use existing human feedback if available. Otherwise create a Review App labeling session for a curated dataset of these traces. Assign domain experts, write concrete labeling instructions, allow rationale comments, and share the session URL. The label schema **name must exactly match the judge name** used to score those traces; `align()` pairs human and judge feedback by that name. Confirm labels are present on the traces before alignment.
4. Hold out a separately labeled sample to measure whether alignment improves agreement. Avoid judging the optimizer only on the traces it trained on.

On Databricks, confirm the intended Unity Catalog dataset, experiment, review-app permissions, and assigned users before creating a session. Do not create a dataset in an arbitrary accessible schema. The [bundled evaluation guide](../guide.md) owns dataset creation and evaluation runs; hand off those steps if this guide is only designing the scorer.

## Align and validate

Retrieve the registered judge and labeled traces, then use the installed `Judge.align()` API with a supported optimizer. Check the installed API and current docs before choosing an optimizer or constructor. Choose the embedding model explicitly after checking its availability and token costs; relying on a default can route embeddings to a provider the workspace has not configured.

When configuring MemAlign, inspect the installed parameters for its reflection model, embedding model, and retrieval count. Record those choices with the alignment run so a later judge revision can be compared fairly.

Compare the base and aligned judges against the **same held-out human labels**, including disagreement examples and subgroup failures. Inspect the aligned judge's public instructions and actual outputs, rather than private memory attributes. Episodic memory may load lazily when the judge is first invoked. A lower aligned score on the agent can be correct if the judge now applies stricter expert standards; judge agreement with humans is the measure here.

Register or update the aligned judge according to the user's versioning needs. Keep the base version available until held-out agreement is demonstrated. Then hand the registered judge to the [bundled evaluation guide](../guide.md) for a fresh baseline, optional sampled production scoring, or prompt optimization. Do not mix scores from base and aligned judge versions in a before/after agent comparison.
