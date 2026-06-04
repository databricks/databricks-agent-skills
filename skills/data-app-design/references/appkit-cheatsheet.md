# AppKit binding cheat-sheet

The design guidance in this skill must compile to real code. Use these exact primitives — do
not hand-roll charts, color, or state handling that AppKit already provides. Names verified
against `@databricks/appkit-ui` and `@databricks/appkit` (v0.24) and this repo.

## Charts — `@databricks/appkit-ui/react`

`AreaChart`, `BarChart`, `LineChart`, `PieChart`, `DonutChart`, `RadarChart`, `ScatterChart`,
`HeatmapChart`. Plus low-level `ChartContainer`, `ChartConfig`, `ChartTooltip`,
`ChartTooltipContent`, `ChartLegend`, `ChartLegendContent` for custom compositions.

Common props (UnifiedChartProps):
- `queryKey: string` — bind chart to an Analytics query (query-driven mode), OR
- `data: Table | Record<string, unknown>[]` — pass rows directly (data-driven mode)
- `parameters?: Record<string, unknown>` — query params; wrap values with `sql.*` helpers
- `xKey?`, `yKey?: string | string[]` — axis fields (auto-detected if omitted)
- `colorPalette?: "categorical" | "sequential" | "diverging"` — **use this for semantic color**, don't pass raw colors
- `showLegend?`, `height?` (default 300), `title?`
- Chart-specific: `BarChart` `orientation`/`stacked`; `Line/AreaChart` `smooth`/`showSymbol`/`stacked`; `DonutChart` `innerRadius`.

Map design intent → palette:
- categories that are merely *different* → `colorPalette="categorical"`
- ordered magnitude (low→high) → `colorPalette="sequential"`
- signed variance (good/bad around a midpoint) → `colorPalette="diverging"`

## Data hooks — `@databricks/appkit-ui/react`

```ts
const { data, loading, error } = useAnalyticsQuery(queryKey, parameters?, options?);
// options.format: "JSON" | "ARROW"; options.autoStart (default true)
// useChartData(...) additionally returns { isArrow, isEmpty } for chart-shaped data
```
Queries live as SQL files referenced by `queryKey`; this repo keeps contracts under
`config/queries/*.sql`. Register result/param types via module augmentation in
`shared/appkit-types/analytics.d.ts`.

SQL param helpers — `import { sql } from "@databricks/appkit"`:
`sql.string`, `sql.number`, `sql.boolean`, `sql.date`, `sql.timestamp`, `sql.binary`. Never
string-concatenate user input into SQL — always parameterize.

## Genie / AI surface — `@databricks/appkit-ui/react`

```tsx
<GenieChat alias="default" basePath="/api/genie" placeholder="Ask about your data…" />
```
Custom UI: `useGenieChat({ alias })` returns `{ messages, status, sendMessage, error,
fetchPreviousPage, ... }` where `status ∈ "idle"|"loading-history"|"streaming"|"error"`. Each
`GenieMessageItem` carries `queryResults` (the generated SQL + result) and `attachments` — surface
these for trust (show the SQL, link results), don't hide them. Compose with `GenieChatInput`,
`GenieChatMessageList`, `GenieQueryVisualization`.

## This repo's component library — `@/components/library`

- `KpiCard` — Card shell: `title, description, value, unit, delta?{label,tone}, size?` + `children` slot. `tone: "positive"|"negative"|"neutral"|"internal"`.
- `MetricTrendCard` — KpiCard + inline `LineChart`; **already renders actual = solid line, comparison = dashed line** (IBCS-style). `metric.trend: [{label,value,comparison?}]`.
- `HistoricalTrendCard` — KpiCard + `AreaChart`; **actual = solid area, comparison = dashed line, target = dashed `ReferenceLine`** (IBCS-style), supports `breakdowns`, `summary`, `formatValue`, `footnote`.
- `DistributionCard` — KpiCard + horizontal stacked bar + legend with percentages; `segments:[{label,value,suffix?,color?}]`.

**Reuse these before inventing new ones.** They already encode the notation rules in this skill.

## Semantic tokens (active palette comes from AppKit-UI `styles.css`)

> Note: `client/src/index.css` has a commented-out custom palette; the live tokens are AppKit-UI's.

- Good / up-is-good: `--success`; Bad / breach: `--destructive`; Caution: `--warning`
- Actual / primary series: `--foreground`; Comparison / secondary: `--muted-foreground`
- Brand / internal series: `--primary`
- Categorical series: `--chart-cat-1..8` (legacy alias `--chart-1..8`); Sequential: `--chart-seq-1..8`; Diverging: `--chart-div-1..8`
- Surfaces: `--background`, `--card`, `--border`, `--muted`; all have light + dark values.

Use tokens via `var(--token)` or the `colorPalette` prop. Never hardcode hex; never use color
that doesn't encode meaning.

## UI primitives — `@databricks/appkit-ui/react` (shadcn, "new-york")

`Card/CardHeader/CardTitle/CardDescription/CardContent/CardAction/CardFooter`, plus `Badge,
Button, Tabs, Table, Select, Skeleton, Empty, Spinner, Tooltip, Sidebar, Sheet, Separator,
Switch, ToggleGroup`, etc. Use `Skeleton` for loading, `Empty` for empty states. Icons: `lucide-react`.
