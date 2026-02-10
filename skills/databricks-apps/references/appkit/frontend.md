# Frontend Guidelines

**For full component API**: `npx @databricks/appkit docs ./docs/docs/api/appkit-ui.md`

## Common Anti-Patterns

These mistakes appear frequently — check the official docs for actual prop names:

| Mistake | Why it's wrong | What to do |
|---------|---------------|------------|
| `xAxisKey`, `dataKey` on charts | Recharts naming, not AppKit | Check docs: `npx @databricks/appkit docs ./docs/docs/api/appkit-ui/data/BarChart.md` |
| `yAxisKeys`, `yKeys` on charts | Recharts naming | Same as above — look for actual prop names |
| `config` on charts | Not a valid prop | Use `options` for ECharts overrides, or individual props |
| `<XAxis>`, `<YAxis>` children | AppKit charts are ECharts-based, NOT Recharts wrappers — configure via props only |  |
| `data`, `columns` on DataTable | DataTable fetches data automatically | Use `queryKey` + `parameters` |
| Double-fetching with `useAnalyticsQuery` + chart component | Components handle their own fetching | Just pass `queryKey` to the component |

**Always verify props against docs before using a component.**

## Key Concepts

- All visualization components (`BarChart`, `LineChart`, `DataTable`, etc.) handle data fetching, loading states, and error handling internally
- Charts are **ECharts-based** — configure via props, not children
- Components support both query mode (`queryKey` + `parameters`) and static data mode (`data` prop)

```typescript
// ✅ Typical usage — component handles everything
<BarChart queryKey="sales_by_region" parameters={{}} />

// ❌ Don't double-fetch
const { data } = useAnalyticsQuery('sales_data', {});
return <BarChart queryKey="sales_data" parameters={{}} />;  // fetches again!
```

## DataTable

DataTable fetches data automatically — don't pass `data` or `columns` props.

**For full props**: `npx @databricks/appkit docs ./docs/docs/api/appkit-ui/data/DataTable.md`

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
