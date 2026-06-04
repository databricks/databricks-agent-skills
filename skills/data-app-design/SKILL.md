---
name: data-app-design
description: Design or critique the UX of Databricks analytics/BI/AI data apps — dashboards, KPI/overview pages, reports, metric pages, and Genie/natural-language data surfaces — and turn the design into concrete AppKit components. Use when laying out a dashboard or report, choosing charts/KPIs, reviewing dashboard/report UX, or designing a Genie/AI data experience. NOT for generic frontend (forms, settings, marketing pages), and NOT for scaffolding/build/deploy of an app — use the databricks-apps skill for those.
metadata:
  version: 0.1.0
  parent: databricks-apps
---

# Data App Design

Make Databricks data + AI apps that communicate clearly and compile to real AppKit code. This
skill merges two bodies of knowledge and binds them to implementation:

- **Composition** — what to show, how much to abstract, how to lay it out → `references/dashboard-patterns.md`
- **Notation** — make comparable things look comparable; honest scales; scenario marks → `references/ibcs-notation.md`
- **Implementation** — the exact AppKit components, hooks, and tokens to use → `references/appkit-cheatsheet.md`

Design advice that doesn't name a real component is incomplete. Always end at a component plan.

## When to use / when NOT
- USE for: dashboard/overview/KPI pages, reports, metric/ontology pages, variance analysis, and Genie/NL data surfaces — design *or* critique.
- Do NOT use for: generic frontend (forms, auth, settings, marketing), or scaffolding/build/deploy (→ `databricks-apps`). If a request is "add a form" or "deploy this", this skill should not fire.
- Relationship: `databricks-apps` builds/runs the app; this skill decides what the data screens should look like and which primitives realize them.

## Workflow
1. **Frame** — audience, the decision/question, refresh cadence, device, primary task. One sentence.
2. **Genre** — pick the closest from `dashboard-patterns.md` (static / analytic / magazine / infographic / repository / embedded mini). State it.
3. **Compose** — choose content + composition patterns (data abstraction, meta-info, layout, interaction, color). Make the tradeoff explicit: what's summarized, hidden, paginated, or made interactive — and why.
4. **Apply notation** — run the relevant `ibcs-notation.md` rules: message-in-title, scenario marks (actual/PY/plan/forecast), honest scales, semantic color. On any chart-vocabulary conflict, **IBCS wins** (see the conflict note in that file).
5. **Bind to components** — map every element to a real primitive from `appkit-cheatsheet.md`. **Reuse `KpiCard`/`MetricTrendCard`/`HistoricalTrendCard`/`DistributionCard` before inventing** — they already encode the notation. Use `colorPalette` + semantic tokens, never hardcoded hex. Bind data with `useAnalyticsQuery`/`queryKey` + `sql.*` params.
6. **Cover the states** — every data view must handle loading / empty / error / partial (see checklist).
7. **Review** — run the checklists in both reference files; lead critiques with the highest-impact comprehension or integrity issue, citing the affected component/file.

## Required states & data realism (non-negotiable for data apps)
- **Loading** → `Skeleton`; **Empty** → `Empty` with a useful next action; **Error** → inline message, never a blank panel; **Partial/stale** → show what you have + a freshness note.
- Every KPI shows unit + period + comparison + **freshness/source** (mirror the metric definition; don't show a number with no provenance).
- Large tables → server-side pagination/sort/filter, not client-side over a huge result set.
- Long-running queries → optimistic loading + timeout/error UX.

## AI / Genie surfaces (the "AI" half)
- Use `<GenieChat alias="…">` or `useGenieChat`; surface `status` as streaming UI, not a frozen spinner.
- **Build trust:** show the generated SQL (`queryResults`), link/show source tables (`attachments`), and add a "verify — AI-generated" disclaimer. Never present an AI answer as ground truth with no way to inspect it.
- Handle the `"error"` status and empty/ambiguous answers explicitly.

## Output formats

**Design proposal:**
```markdown
## Direction
[Genre, audience, primary task, design intent.]
## Pattern & notation choices
- Composition: [data info, meta info, layout, interaction, color]
- Notation: [message, scenario marks, scales, semantic color]
## Component plan        ← the part that makes it buildable
- [element] → [AppKit component] (queryKey/props), [token/palette], states handled
## Tradeoffs & risks
[What's summarized/hidden/paginated/interactive; overload, scale, a11y, maintenance risks.]
```

**Critique:** lead with the top comprehension/integrity issue, cite the component/file, then list
findings by impact, each with the concrete fix (which component/token/state to change).

## Anti-patterns
- Producing a design memo with no component plan.
- "Use semantic color" without naming the token/palette.
- Inventing a chart when a library card already does it (and already follows IBCS).
- Adding interaction, pages, or density the task doesn't need (over-engineering a mock-first app).
- Forgetting loading/empty/error states, or KPIs with no freshness/source.
