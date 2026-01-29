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

```typescript
import { createApp, server, analytics } from '@databricks/app-kit';

const app = await createApp({
  plugins: [
    server({ autoStart: false }),
    analytics(),
  ],
});

// Extend with custom tRPC endpoints if needed
app.server.extend((express: Application) => {
  express.use('/trpc', [appRouterMiddleware()]);
});

await app.server.start();
```

## useAnalyticsQuery Hook

**ONLY use when displaying data in a custom way that isn't a chart or table.**

Use cases:
- Custom HTML layouts (cards, lists, grids)
- Summary statistics and KPIs
- Conditional rendering based on data values
- Data that needs transformation before display

**⚠️ CRITICAL: This is NOT React Query**

| React Query Pattern | AppKit Pattern |
|---------------------|----------------|
| `{ enabled: !!id }` | ❌ NOT SUPPORTED - Use conditional rendering |
| `refetch()` | ❌ NOT SUPPORTED - Change parameters or re-mount |
| `onSuccess` callback | ❌ NOT SUPPORTED - Use useEffect on data |

**Conditional Query Pattern:**

```typescript
// ❌ WRONG - enabled option doesn't exist
const { data } = useAnalyticsQuery('details', params, { enabled: !!selectedId });

// ✅ CORRECT - Use conditional rendering
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

**Basic Usage:**

```typescript
import { useAnalyticsQuery, Skeleton } from '@databricks/app-kit-ui/react';

interface QueryResult { column_name: string; value: number; }

function CustomDisplay() {
  const { data, loading, error } = useAnalyticsQuery<QueryResult[]>('query_name', {
    start_date: sql.date(Date.now()),
    category: sql.string("tools")
  });

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
