# Frontend Guidelines

**For full component API**: run `npx @databricks/appkit docs` and navigate to the component you need.

## Common Anti-Patterns

These mistakes appear frequently — check the official docs for actual prop names:

| Mistake | Why it's wrong | What to do |
|---------|---------------|------------|
| `xAxisKey`, `dataKey` on charts | Recharts naming, not AppKit | Check docs for correct prop names |
| `yAxisKeys`, `yKeys` on charts | Recharts naming | Same — use docs |
| `config` on charts | Not a valid prop | Use `options` for ECharts overrides, or individual props |
| `<XAxis>`, `<YAxis>` children | AppKit charts are ECharts-based, NOT Recharts wrappers — configure via props only |  |
| `data`, `columns` on DataTable | DataTable fetches data automatically | Use `queryKey` + `parameters` |
| Double-fetching with `useAnalyticsQuery` + chart component | Components handle their own fetching | Just pass `queryKey` to the component |

**Always verify props against docs before using a component.**

## Chart Props Quick Reference

All charts accept these core props (verify full list via docs links above):

```tsx
<BarChart
  queryKey="sales_by_region"   // SQL query filename without .sql
  parameters={{}}              // query params — REQUIRED even if empty
  xKey="region"                // column name for X axis
  yKey="revenue"               // column name for Y axis (string or string[] for multi-series)
  colors={['#40d1f5']}         // custom colors
  height={400}                 // default: 300
/>

<LineChart queryKey="monthly_trend" parameters={{}} xKey="month" yKey={["revenue", "expenses"]} />
```

Charts are **ECharts-based** — configure via props, not Recharts-style children. Components handle data fetching, loading, and error states internally.

> ⚠️ **`parameters` is REQUIRED on all data components**, even when the query has no params. Always include `parameters={{}}`.

```typescript
// ❌ Don't double-fetch
const { data } = useAnalyticsQuery('sales_data', {});
return <BarChart queryKey="sales_data" parameters={{}} />;  // fetches again!
```

## DataTable

DataTable fetches data automatically — don't pass `data` or `columns` props.

**For full props**: check AppKit docs (DataTable page).

```tsx
// ❌ WRONG - missing required `parameters` prop
<DataTable queryKey="my_query" />

// ❌ WRONG - DataTable fetches its own data
<DataTable queryKey="my_query" parameters={{}} data={rows} columns={cols} />

// ✅ CORRECT
<DataTable queryKey="my_query" parameters={{}} />
```

**Custom column formatting** — use the `transform` prop or format in SQL:

```typescript
<DataTable
  queryKey="products"
  parameters={{}}
  transform={(data) => data.map(row => ({
    ...row,
    price: `$${Number(row.price).toFixed(2)}`,
  }))}
/>
```

## Available Components (Quick Reference)

**For full prop details**: `npx @databricks/appkit docs` → navigate to `./docs/docs/api/appkit-ui/data/` for charts/tables, `./docs/docs/api/appkit-ui/ui/` for UI components.

### Data Components (`@databricks/appkit-ui/react`)

| Component | Key Props | Use For |
|-----------|-----------|---------|
| `BarChart` | `queryKey`, `parameters`, `xKey`, `yKey`, `colors`, `height` | Categorical comparisons |
| `LineChart` | `queryKey`, `parameters`, `xKey`, `yKey`, `colors` | Time series, trends |
| `AreaChart` | `queryKey`, `parameters`, `xKey`, `yKey` | Cumulative/stacked trends |
| `PieChart` | `queryKey`, `parameters`, `xKey`, `yKey`, `innerRadius`, `showLabels` | Part-of-whole |
| `DataTable` | `queryKey`, `parameters`, `transform` | Tabular data display |

### UI Components (`@databricks/appkit-ui/react`)

| Component | Common Props |
|-----------|-------------|
| `Card`, `CardHeader`, `CardTitle`, `CardContent` | Standard container |
| `Badge` | `variant`: "default" \| "secondary" \| "destructive" \| "outline" |
| `Button` | `variant`, `size`, `onClick` |
| `Input` | `placeholder`, `value`, `onChange` |
| `Select`, `SelectTrigger`, `SelectContent`, `SelectItem` | Dropdown; `SelectItem` value cannot be "" |
| `Skeleton` | `className` — use for loading states |
| `Separator` | Visual divider |
| `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` | Tabbed interface |

All data components **require `parameters={{}}`** even when the query has no params.

## Layout Structure

```tsx
<div className="container mx-auto p-4">
  <h1 className="text-2xl font-bold mb-4">Page Title</h1>
  <form className="space-y-4 mb-8">{/* form inputs */}</form>
  <div className="grid gap-4">{/* list items */}</div>
</div>
```

## Component Organization

- Shared UI components: `@databricks/appkit-ui/react`
- Feature components: `client/src/components/FeatureName.tsx`
- Split components when logic exceeds ~100 lines or component is reused

## Gotchas

- `SelectItem` cannot have `value=""`. Use sentinel value like `"all"` for "show all" options.
- Use `<Skeleton>` components instead of plain "Loading..." text
- Handle nullable fields: `value={field || ''}` for inputs
- For maps with React 19, use react-leaflet v5: `npm install react-leaflet@^5.0.0 leaflet @types/leaflet`

Databricks brand colors: `['#40d1f5', '#4462c9', '#EB1600', '#0B2026', '#4A4A4A', '#353a4a']`
