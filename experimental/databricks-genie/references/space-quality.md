# Building High-Quality Genie Spaces

How to size, build, validate, and harden a Genie Space. These practices apply to any space; where a space is backed by **metric views**, pair them with the design rules in [databricks-metric-views/genie-integration.md](../../databricks-metric-views/references/genie-integration.md) and the query rules in [databricks-metric-views/query-patterns.md](../../databricks-metric-views/references/query-patterns.md).

> **This is the condensed, tool-agnostic reference** for the programmatic / MCP path. If you're working **inside Databricks Genie Code**, the in-product skills are the authority and go far deeper — use [create-genie-space](../create-genie-space/SKILL.md) (design), [diagnose-genie-space](../diagnose-genie-space/SKILL.md) (root-cause), [optimize-genie-space](../optimize-genie-space/SKILL.md) (benchmark-driven tuning), and [optimize-genie-query](../optimize-genie-query/SKILL.md) (query performance). This page summarizes the same principles for when those product-native tools aren't in play.

## Space Sizing

- **Hard limit:** 30 tables/views/metric views per Genie space.
- **Practical guidance:** Keep spaces focused — the tighter the domain, the better Genie performs.
- Organize spaces by **business domain/subdomain**, not by report. A domain (e.g. "Marketing") maps to a space; if a domain is broad, split by subdomain (e.g. "Online Marketing").
- If a domain approaches 30 items, split it into multiple Genie spaces by subdomain.
- Assign domain/subdomain tags to both Genie spaces and their underlying tables/metric views for discoverability and observability.
- Optional: mirror the hierarchy in Unity Catalog — one schema per domain or subdomain.

## Incremental Build & Validation Workflow

Add and validate **one measure/question at a time**. Skipping this is the most common cause of broken spaces — when you add many at once you can't isolate which addition confused Genie.

```text
For each KPI / question:
  1. Add ONE measure (or one metric view) to the space
  2. Ask sample questions in the Genie space
  3. Compare Genie's result against the source-of-truth report
  4. Save the validated query as an EXAMPLE SQL in the space
  5. Add 2-4 phrasings of the question to BENCHMARKS with ground-truth SQL
  6. Run regression tests
  7. Only then add the next measure
```

### Example SQL: Keep It Simple

Saved example queries are reused and imitated by Genie. Simpler example SQL → less reasoning load → better answers.

- Prefer `WHERE` over `CASE` when both work.
- Avoid unnecessary subqueries or window functions in examples.
- Use the `MEASURE()` syntax correctly: `` MEASURE(`Total Revenue`) `` — and follow the [metric-view query rules](../../databricks-metric-views/references/query-patterns.md) (no measures in `WHERE`/`GROUP BY`, group dimensions used in `CASE` alongside `MEASURE()`).

### Benchmarks: 2-4 Phrasings per Question

Users phrase the same question different ways. For each validated measure, add to benchmarks:

- 2-4 phrasings of the same question
- The same ground-truth SQL for all phrasings
- More variations (5+) for complex or ambiguous questions

Test with variations in casing, filter shorthand (MTD/YTD/QTD), and alternative business terminology.

### Regression Testing

- Rerun all benchmarks after **every** change (new KPI, new instruction, new synonym).
- A previously passing benchmark that now fails almost always means the latest addition confused Genie.
- Use Genie's failure analysis and "Review Proposed Fix" features to diagnose.
- For multi-Genie setups (supervisor agents, multi-agent systems), use Databricks One Chat or [MLflow agent evaluation](https://docs.databricks.com/en/generative-ai/agent-evaluation/) for cross-space regression.

## Genie Space Setup Checklist

- [ ] **Space description is set.** Required for multi-agent routing — without it, supervisor agents cannot delegate reliably.
- [ ] **Prompt matching is enabled** on relevant columns so Genie matches user language to actual data values and corrects misspellings.
- [ ] **SQL expressions** are defined for ambiguous categorical values, with trigger conditions and exact-match instructions.
- [ ] **Instructions follow the pattern:** (1) trigger condition — "when user asks about X", (2) required action — "always do Y", (3) example — sample question + expected behavior.
- [ ] **Base views and raw fact tables are removed** from the space once metric views exist on top of them — otherwise Genie sees unaggregated rows and must re-derive aggregation logic.

## Anti-Patterns

| Anti-pattern | Why it fails | Fix |
|--------------|--------------|-----|
| Both the base view AND the metric view in the same space | Genie sees unaggregated rows and must re-derive aggregation logic | Remove the base view from the space |
| Adding 10 measures at once before testing | Can't isolate which one broke Genie's reasoning | Add and validate one at a time |
| Genie space with no description | Multi-agent routing fails silently | Always set a space description |
| Complex `CASE` chains in saved example SQL | Increases Genie's reasoning load on similar questions | Simplify to `WHERE` filters; lean on composed measures |
