---
name: databricks-app-design
parent: databricks-apps
description: Design the UX of Databricks data apps — dashboards, KPI pages, reports, charts, tables, and Genie/chat data assistants — mapped to concrete AppKit components. Use when BUILDING or reviewing any UI that displays data or answers data questions: choosing genre, layout, charts, KPIs, semantic color, required states (loading/empty/error), IBCS notation, and AI-result trust (showing generated SQL/sources for Genie/chat). NOT for authoring managed AI/BI (Lakeview) dashboards (→ databricks-aibi-dashboards), non-data frontend (forms, settings, auth, marketing), or scaffolding/build/deploy (→ databricks-apps). Complements databricks-apps; use it alongside whenever the app has a dashboard, chart, table, KPI, report, or Genie/chat/AI surface.
metadata:
  version: 0.1.0
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
- Do NOT use for: authoring managed **AI/BI (Lakeview) dashboards** (→ `databricks-aibi-dashboards`), generic frontend (forms, auth, settings, marketing), or scaffolding/build/deploy (→ `databricks-apps`). If a request is "add a form", "deploy this", or "build a Lakeview / AI-BI dashboard", this skill should not fire.
- Relationship: `databricks-apps` builds/runs the app; this skill decides what the data screens should look like and which primitives realize them.

## Workflow
1. **Frame** — audience, the decision/question, refresh cadence, device, primary task. One sentence.
2. **Genre** — pick the closest from `dashboard-patterns.md` (static / analytic / magazine / infographic / repository / embedded mini). State it.
3. **Compose** — choose content + composition patterns (data abstraction, meta-info, layout, interaction, color). Make the tradeoff explicit: what's summarized, hidden, paginated, or made interactive — and why.
4. **Apply notation** — run the relevant `ibcs-notation.md` rules: message-in-title, scenario marks (actual/PY/plan/forecast), honest scales, semantic color. On any chart-vocabulary conflict, **IBCS wins** (see the conflict note in that file).
5. **Bind to components** — map every element to a primitive that's actually **exported from `@databricks/appkit` / `@databricks/appkit-ui`** (see `appkit-cheatsheet.md`); never cite a component AppKit doesn't ship. There's no prebuilt KPI/trend/distribution card — compose those from primitives, following the notation rules. Use `colorPalette` + semantic tokens, never hardcoded hex. Bind data with `useAnalyticsQuery`/`queryKey` + `sql.*` params.
6. **Cover the states** — every data view must handle loading / empty / error / partial (see checklist).
7. **Review** — run the checklists in both reference files; lead critiques with the highest-impact comprehension or integrity issue, citing the affected component/file.

## Required states & data realism (non-negotiable for data apps)
- **Loading** → `Skeleton`; **Empty** → `Empty` with a useful next action; **Error** → inline message, never a blank panel; **Partial/stale** → show what you have + a freshness note.
- Every KPI shows unit + period + comparison + **freshness/source** (mirror the metric definition; don't show a number with no provenance).
- Large tables → server-side pagination/sort/filter, not client-side over a huge result set.
- Long-running queries → optimistic loading + timeout/error UX.

## AI / Genie surfaces (the "AI" half)
**Gate:** this section applies **only** if the app has a Genie / chat / natural-language / "ask your data" surface. For a pure dashboard / KPI / report app with no conversational input, **skip this section and `references/genie-ai-trust.md` entirely.** When it does apply, implement ALL five (code in `references/genie-ai-trust.md`):
A Genie/chat/NL answer is only trustworthy if the user can see how it was produced and who it ran as. "Use `GenieChat` + a spinner" is NOT enough — for ANY Genie/chat surface, ship all five (copy the exact snippets from the reference):
1. **Identity** — a `/api/whoami` route (real `x-forwarded-email`/`x-forwarded-user` headers) + the signed-in user in a `Badge`. Claim OBO **only if `user_api_scopes: [dashboards.genie]` is wired**; otherwise disclose the query runs as the app's service principal.
2. **Generated SQL** — render `attachments[].query` in an inspectable "Generated SQL" `Card`; never hide how the answer was computed.
3. **Streaming/status** — reflect `useGenieChat().status` (`streaming`/`error`), never a frozen spinner.
4. **Disclaimer** — a persistent "AI-generated — verify" note per answer.
5. **Governance + states** — `genie()` space config + a truthful execution-identity note (OBO when user-scoped, else service principal) + empty/error/ambiguous handling (`Empty`, `Alert`).

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
- Naming a component AppKit doesn't export (e.g. a prebuilt `KpiCard`) — compose composites from published primitives instead.
- Adding interaction, pages, or density the task doesn't need (over-engineering a mock-first app).
- Forgetting loading/empty/error states, or KPIs with no freshness/source.
