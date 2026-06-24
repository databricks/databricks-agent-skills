# Genie Failure Routing

Use this reference to classify Genie Agent failures and choose the smallest useful fix.

## Evidence To Gather

- Relevant table, view, and Metric View identifiers and descriptions.
- Metric View measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and formatting.
- Table and column descriptions, synonyms, prompt matching settings, and hidden fields.
- Join specs and comments for raw tables exposed together.
- SQL snippets, example SQL, SQL functions, and text instructions.
- Similar benchmark questions, SQL answers, evaluation notes, and execution mode, if present.
- Benchmark inventory size, duplicate clusters, coverage categories, difficulty levels, and whether the set is too small, too narrow, too easy, or too large for practical iteration.
- Monitor-tab feedback signals: thumbs up/down trends, negative ratings, `Fix it`, `Request review`, needs-review conversations, feedback comments, reviewer comments, repeated user phrasing, generated SQL or error text from reviewable conversations, and private-conversation limitations.
- Agent-mode final reports, research steps, supporting query outputs, citations, tables, charts, and assessment notes when applicable.
- Read-only checks for data types, categorical values, null rates, cardinality, join grain, and Metric View query behavior when needed.

## Routing Order

1. Data source scope and descriptions.
2. Metric View semantic model and agent-facing metadata.
3. Table and column metadata.
4. Prompt matching for categorical value confusion.
5. Join specs for raw-table relationships.
6. SQL snippets for reusable business logic.
7. Example SQL for complex patterns.
8. SQL functions for trusted complex logic.
9. Short response-quality instructions only for global Agent-report behavior.
10. Text instructions only for global conventions.

## Feedback Routing

Use feedback as evidence for clustering failures, not as a tuning surface. Do not recommend changing feedback, comments, review status, or conversation history as the fix.

Translate feedback patterns into the existing repair levers:

- Repeated negative feedback on the same source, Metric View, measure, dimension, filter, join, or time pattern: classify the underlying wrong source, semantic model, filter, join, business logic, or time logic failure before choosing the fix.
- Review requests with missing SQL, wrong SQL, failed SQL, or unsupported final answers: inspect the generated SQL/error and route to the smallest structured surface that would prevent the same failure.
- User comments that explain a business term, synonym, category label, KPI definition, fiscal period, or expected result shape: treat the comment as business-intent evidence and encode the durable rule in metadata, Metric View semantics, prompt matching, snippets, representative examples, or short global instructions.
- High negative-feedback volume with weak or missing benchmark coverage: recommend benchmark repair or benchmark additions before benchmark-driven tuning, and use feedback clusters to choose representative benchmark candidates.
- Feedback that contradicts passing benchmark results: check whether benchmarks are stale, too narrow, too easy, missing Agent evaluation notes, or failing to cover real user phrasing before trusting the benchmark signal.
- Private conversations or unavailable Monitor details: use visible prompt, status, rating, timestamp, and trend metadata only; lower confidence and state the limitation.

## Failure Classes

### Wrong Data Source Or Field

Symptoms: wrong table, Metric View, column, measure, or dimension; raw table chosen when a governed Metric View should answer; important source omitted; repeated feedback says Genie used the wrong data source or field.

Fix: clarify source and field descriptions, synonyms, and source boundaries; hide irrelevant fields; add example SQL only for complex patterns.

### Wrong Metric View Measure, Dimension, Scope, Or Grain

Symptoms: wrong `MEASURE()` call, invalid grouping, missed persistent filter, wrong time dimension, incorrect semiadditive or rolling logic; feedback clusters around a governed KPI, grouping, scope, or grain mismatch.

Fix: improve Metric View names, comments, display names, synonyms, formats, filters, dimensions, window measures, or upstream joins. Add Genie examples only after the governed source is clear.

### Wrong Filter Value

Symptoms: invalid category, wrong code or label, casing mismatch, misunderstood business term; user feedback names the expected label, code, synonym, or filter scope.

Fix: enable prompt matching only for eligible useful categorical strings, add synonyms, or add a reusable filter snippet when a business term maps to SQL logic.

### Wrong Join

Symptoms: missing table, wrong key, duplicate rows, changed grain, unsupported bridge or self-join; feedback or review comments mention duplicated rows, missing related records, or impossible cross-source combinations.

Fix: add or clarify raw-table join specs backed by constraints, naming, row-count checks, or user confirmation. For complex recurring joins, recommend an upstream view or Metric View.

### Business Logic Or Time Logic Error

Symptoms: wrong numerator, denominator, aggregation, fiscal period, date boundary, rolling window, ranking, or answer shape; feedback supplies the expected KPI definition, time convention, ranking rule, or result shape.

Fix: use snippets for reusable expressions or filters, Metric View measures for governed metrics, and representative example SQL for complex multi-step shapes.

### Weak Agent-Mode Report

Symptoms: incomplete research plan, too few supporting queries, weak evidence, unsupported causal claims, missing citations, missing supporting table/chart, poor synthesis, missing caveats, or review requests for unsupported Agent-mode conclusions.

Fix: improve source and Metric View descriptions, clarify metric and dimension semantics, add representative examples for reusable investigative patterns, or add a short global response-quality instruction only when the problem is not source-specific.

### Benchmark Ground Truth Problem

Symptoms: invalid SQL answer, missing SQL for a deterministic Chat benchmark, unclear or missing evaluation note for an Agent-style benchmark, a multi-query analysis question forced into a single SQL answer, or benchmark pass rates that conflict with recent negative user feedback on the same pattern.

Fix: repair benchmark definitions outside Genie tuning. Use checked SQL for deterministic tabular questions, evaluation notes for Agent-style multi-step analysis, and both only when the same question has a single canonical result plus full-response quality criteria.

### Benchmark Set Too Large Or Redundant

Symptoms: too many questions for practical benchmark iteration, many near-duplicates that only swap dates or category literals, one source or metric overweighted, too many trivial lookup questions, repeated variants that obscure root-cause patterns, or feedback clusters showing important real user patterns missing from the benchmark.

Fix: recommend a dedicated benchmark pruning pass outside Genie tuning. Retain a representative set that preserves diversity, source and metric coverage, answer shapes, historically fragile behavior, and a meaningful mix of medium and hard questions, with only a small number of easy smoke tests. Record pruned question IDs and the coverage or difficulty rationale.

### Instruction Conflict Or Overload

Symptoms: examples, snippets, benchmarks, feedback-derived assumptions, or text instructions conflict; text instructions contain a long source-specific rulebook.

Fix: move specific logic into structured surfaces and keep text instructions short, global, and non-overlapping.

## Health Signals

Treat these as blockers or warnings during diagnosis:

- Too many overlapping data sources.
- Generic table, Metric View, or column descriptions.
- Important categorical filters without prompt matching.
- Raw tables exposed together with missing joins.
- Example SQL that copies benchmark questions.
- High negative-feedback or review-request volume for patterns with weak benchmark coverage.
- Feedback comments that repeatedly define business terms missing from metadata, Metric Views, prompt matching, snippets, examples, or short global instructions.
- Passing benchmark results that contradict recent negative feedback on equivalent real user questions.
- Benchmark set too small, too narrow, too easy, too redundant, too large for practical iteration, missing checked SQL answers for deterministic Chat execution, or missing evaluation notes for Agent-style questions.
- Text instructions containing source-specific SQL logic.
