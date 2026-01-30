# Frontend Guidelines

## ⚠️ INVALID PROPS - Read First

These props DO NOT exist on AppKit components:

| Component | Invalid Props | Use Instead |
|-----------|--------------|-------------|
| DataTable | `data`, `columns` | `queryKey` + `parameters` (fetches automatically) |
| All Charts | `seriesKey`, `nameKey`, `valueKey`, `dataKey` | `xKey`, `yKey` |
| All Charts | `<XAxis>`, `<YAxis>`, `<CartesianGrid>` children | Props only (ECharts, not Recharts) |

## Visualization Components

Components from `@databricks/appkit-ui/react` handle data fetching, loading states, and error handling internally.

Available: `AreaChart`, `BarChart`, `LineChart`, `PieChart`, `RadarChart`, `DataTable`

**⚠️ CRITICAL: AppKit charts are ECharts-based, NOT Recharts wrappers**

```typescript
// ❌ WRONG - Charts do NOT accept Recharts children
<BarChart queryKey="data" parameters={{}}>
  <CartesianGrid />  // Not supported
  <XAxis dataKey="x" />  // Not supported
</BarChart>

// ✅ CORRECT - Use props for customization
<BarChart
  queryKey="data"
  parameters={{}}
  xKey="region"                    // X-axis field
  yKey={["revenue", "expenses"]}   // Y-axis field(s) - string or string[]
  colors={['#40d1f5', '#4462c9']}  // Custom colors
  stacked                          // Stack bars
  orientation="horizontal"         // "vertical" (default) | "horizontal"
  showLegend                       // Show legend
  height={400}                     // Height in pixels (default: 300)
/>
```

**Chart Props Reference:**

For full props API, see: `npx @databricks/appkit docs ./docs/docs/api/appkit-ui/data/BarChart.md`

Common props: `queryKey`, `parameters`, `xKey`, `yKey`, `colors`, `height`, `showLegend`, `stacked`

**Basic Usage:**

```typescript
import { BarChart, LineChart, DataTable, Card, CardContent, CardHeader, CardTitle } from '@databricks/appkit-ui/react';
import { sql } from "@databricks/appkit-ui/js";

function MyDashboard() {
  return (
    <div>
      <Card>
        <CardHeader><CardTitle>Sales by Region</CardTitle></CardHeader>
        <CardContent>
          <BarChart queryKey="sales_by_region" parameters={{}} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Revenue Trend</CardTitle></CardHeader>
        <CardContent>
          <LineChart
            queryKey="revenue_over_time"
            parameters={{ months: sql.number(12) }}
            xKey="month"
            yKey={["revenue", "expenses"]}
            colors={['#40d1f5', '#4462c9']}
            showLegend
          />
        </CardContent>
      </Card>
    </div>
  );
}
```

Components automatically fetch data, show loading states, display errors, and render with sensible defaults.

Databricks brand colors: `['#40d1f5', '#4462c9', '#EB1600', '#0B2026', '#4A4A4A', '#353a4a']`

**❌ Don't double-fetch:**

```typescript
// WRONG - redundant fetch
const { data } = useAnalyticsQuery('sales_data', {});
return <BarChart queryKey="sales_data" parameters={{}} />;

// CORRECT - let component handle it
return <BarChart queryKey="sales_data" parameters={{}} />;
```

## DataTable Component

**DataTable fetches data automatically** - you don't pass `data` or `columns` props!

```typescript
// ❌ WRONG - DataTable doesn't accept data/columns props
<DataTable
  data={myData}
  columns={[{ header: 'Name', accessor: 'name' }]}
/>

// ✅ CORRECT - DataTable fetches from query
<DataTable
  queryKey="users_list"
  parameters={{}}
  filterColumn="email"              // Column to filter by
  filterPlaceholder="Search..."     // Filter input placeholder
  pageSize={25}                     // Rows per page
  pageSizeOptions={[10, 25, 50]}    // Page size options
/>
```

**Custom column formatting** - use the `transform` prop or format in SQL:

```typescript
// Option 1: Use transform prop
<DataTable
  queryKey="products"
  parameters={{}}
  transform={(data) => data.map(row => ({
    ...row,
    price: `$${Number(row.price).toFixed(2)}`,
  }))}
/>

// Option 2: Format in SQL query
// SELECT name, CONCAT('$', FORMAT_NUMBER(price, 2)) as price FROM products
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

## Radix UI Constraints

- `SelectItem` cannot have `value=""`. Use sentinel value like `"all"` for "show all" options.

## Map Libraries (react-leaflet)

For maps with React 19, use react-leaflet v5:

```bash
npm install react-leaflet@^5.0.0 leaflet @types/leaflet
```

```typescript
import 'leaflet/dist/leaflet.css';
```

## Best Practices

- Use shadcn/radix components (Button, Input, Card, etc.) for consistent UI, import them from `@databricks/appkit-ui/react`.
- **Use skeleton loaders**: Always use `<Skeleton>` components instead of plain "Loading..." text
- Define result types in `shared/types.ts` for reuse between frontend and backend
- Handle nullable fields: `value={field || ''}` for inputs
- Type callbacks explicitly: `onChange={(e: React.ChangeEvent<HTMLInputElement>) => ...}`
- Forms should have loading states: `disabled={isLoading}`
- Show empty states with helpful text when no data exists
