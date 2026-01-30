# Databricks App Kit SDK

## TypeScript Import Rules

This template uses strict TypeScript settings with `verbatimModuleSyntax: true`. **Always use `import type` for type-only imports**.

Template enforces `noUnusedLocals` - remove unused imports immediately or build fails.

```typescript
// ✅ CORRECT - use import type for types
import type { MyInterface, MyType } from '../../shared/types';

// ❌ WRONG - will fail compilation
import { MyInterface, MyType } from '../../shared/types';
```

## Server Setup

For server configuration, see: `npx @databricks/appkit docs ./docs/docs/plugins.md`

## useAnalyticsQuery Hook

**ONLY use when displaying data in a custom way that isn't a chart or table.**

Use cases:
- Custom HTML layouts (cards, lists, grids)
- Summary statistics and KPIs
- Conditional rendering based on data values
- Data that needs transformation before display

**⚠️ Memoize Parameters to Prevent Infinite Loops:**

```typescript
// ❌ WRONG - creates new object every render → infinite refetch loop
function MyComponent() {
  const { data } = useAnalyticsQuery('query', { id: sql.string(selectedId) });
}

// ✅ CORRECT - memoize parameters
function MyComponent() {
  const params = useMemo(() => ({ id: sql.string(selectedId) }), [selectedId]);
  const { data } = useAnalyticsQuery('query', params);
}
```

**Conditional Query Options:**

| Approach | When to use |
|----------|-------------|
| `{ autoStart: false }` | Prevent query from running on mount, start manually later |
| Conditional rendering | Only mount component when data is needed |

**Option 1: Use `autoStart: false`**

```typescript
const { data, loading, error } = useAnalyticsQuery('details', params, { autoStart: false });
```

**Option 2: Conditional rendering**

```typescript
function ParentComponent() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div>
      <SelectList onSelect={setSelectedId} />
      {selectedId && <DetailsComponent id={selectedId} />}
    </div>
  );
}

function DetailsComponent({ id }: { id: string }) {
  // Query only runs when component is mounted (when id exists)
  const { data, loading, error } = useAnalyticsQuery('details', {
    id: sql.string(id)
  });
  // ...
}
```

**Basic Usage:**

```typescript
import { useAnalyticsQuery, Skeleton } from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { useMemo } from 'react';

interface QueryResult { column_name: string; value: number; }

function CustomDisplay() {
  const params = useMemo(() => ({
    start_date: sql.date('2024-01-01'),
    category: sql.string("tools")
  }), []);

  const { data, loading, error } = useAnalyticsQuery<QueryResult[]>('query_name', params);

  if (loading) return <Skeleton className="h-4 w-3/4" />;
  if (error) return <div className="text-destructive">Error: {error}</div>;

  return (
    <div className="grid gap-4">
      {data?.map(row => (
        <div key={row.column_name} className="p-4 border rounded">
          <h3>{row.column_name}</h3>
          <p>{row.value}</p>
        </div>
      ))}
    </div>
  );
}
```

**API:**

```typescript
const { data, loading, error } = useAnalyticsQuery<T>(
  queryName: string,                        // SQL file name without .sql extension
  params: Record<string, SQLTypeMarker>     // Query parameters
);
// Returns: { data: T | null, loading: boolean, error: string | null }
```
