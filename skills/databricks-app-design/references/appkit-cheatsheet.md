# AppKit binding — design → primitive map

This skill decides **what** to build; AppKit owns the **exact** API. For component names, props,
hook signatures, plugin config, and the live design-token set, query AppKit's own docs — the same
source of truth the parent `databricks-apps` skill mandates ("ALWAYS start here", "DO NOT guess doc
paths"). Do **not** rely on a pinned list here; it drifts with the package version:

```bash
npx @databricks/appkit docs                              # ALWAYS start here — lists every section + doc path
npx @databricks/appkit docs "appkit-ui API reference"    # UI: charts, tables, Genie, shadcn primitives, hooks
npx @databricks/appkit docs ./docs/plugins/analytics.md  # backend: analytics plugin, sql helpers, queryKey
```

Use this file for the design→primitive mapping; confirm the exact signatures against those docs.

## Charts
Bind charts to data; never hand-roll SVG/`<canvas>`. AppKit-ui ships ECharts-based chart components
(`BarChart`/`LineChart`/`AreaChart`, plus others — confirm the exact set in the docs). Each takes
either `queryKey` + `parameters` (query-driven; `parameters` is required, even `{}`) or static `data`,
plus a `colorPalette` prop. Map design intent → palette:
- categories that are merely *different* → categorical palette
- ordered magnitude (low→high) → sequential palette
- signed / good-bad variance around a midpoint → diverging palette

Pass `colorPalette` (or semantic tokens) — never raw hex or raw Tailwind color utilities.

## Data
Fetch with AppKit's analytics query hook (returns `{ data, loading, error }`). Define queries as SQL
files under `config/queries/*.sql` keyed by `queryKey`, parameterize with the `sql.*` helpers (never
string-concatenate user input), and register result/param types in
`shared/appkit-types/analytics.d.ts`. (Exact hook + helper names: the AppKit docs above.)

## Genie / AI surface
Use AppKit's Genie chat component / `useGenieChat` hook; its messages carry the generated SQL and
attachments. Surface them for trust — see `genie-ai-trust.md` for the required patterns. (Exact
component/hook API: the AppKit docs above.)

## Repo component library — `@/components/library`
When the app already ships these, **reuse them before inventing** — they encode this skill's notation rules:
- `KpiCard` — card shell with title / value / unit / delta(tone).
- `MetricTrendCard` — KpiCard + inline line chart; actual = solid line, comparison = dashed (IBCS).
- `HistoricalTrendCard` — KpiCard + area chart; actual solid, comparison dashed, target dashed reference line; supports breakdowns / summary / footnote.
- `DistributionCard` — KpiCard + horizontal stacked bar + percentage legend.

## Semantic color
Color must encode meaning; use semantic tokens or the chart `colorPalette` prop. **Never use raw colors — neither hex (`#22c55e`) NOR raw Tailwind palette utilities (`bg-amber-100`, `text-emerald-600`, `fill-red-500`, `text-amber-500`, …).** Both bypass the design tokens and break dark mode. Map intent to a token:
- good / up-is-good → `--success`; bad / breach → `--destructive`; caution / warning → `--warning`
- actual / primary series → `--foreground`; comparison / secondary → `--muted-foreground`; brand / internal → `--primary`
- categorical / sequential / diverging chart series → the matching chart-palette tokens (or the `colorPalette` prop)

The exact token names and their light/dark values come from AppKit-ui's stylesheet — read it; don't
hardcode colors or assume token names.

## UI primitives & required states
Use AppKit-ui's shadcn primitives (`Card*`, `Badge`, `Button`, `Tabs`, `Table`, `Select`,
`Separator`, etc.). Every data view must handle its states: loading → `Skeleton`, empty → `Empty`,
error → `Alert`/inline message. Icons: `lucide-react`.
