# Vector Similarity Search with pgvector

Use the pgvector extension in Lakebase for embedding-based similarity search (RAG, semantic search, recommendations).

## Extension Setup

```bash
databricks psql --project <project-name> --profile <PROFILE> -- -c "
  CREATE EXTENSION IF NOT EXISTS vector;
"
```

If you get error code `42501` (insufficient privileges), the extension may already exist — this is safe to ignore in `setupVectorTables()`:

```typescript
try {
  await appkit.lakebase.query("CREATE EXTENSION IF NOT EXISTS vector");
} catch (err: unknown) {
  const code = (err as { code?: string }).code;
  if (code === "42501") {
    console.log("[vectors] Skipping extension creation — insufficient privileges (likely already exists)");
  } else {
    throw err;
  }
}
```

## Table Schema

```sql
CREATE SCHEMA IF NOT EXISTS vectors;

CREATE TABLE IF NOT EXISTS vectors.documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content TEXT NOT NULL,
  embedding VECTOR(1024),
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Dimension matching**: `VECTOR(1024)` must match your embedding model's output dimension. Common Databricks endpoints:
- `databricks-gte-large-en` — 1024 dimensions
- `databricks-bge-large-en` — 1024 dimensions

If using a different model (768d or 1536d), change `VECTOR(1024)` to match.

## Vector Store Module

Create `server/lib/vector-store.ts`:

```typescript
import type { Application } from "express";

interface AppKitWithLakebase {
  lakebase: {
    query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
  };
  server: {
    extend(fn: (app: Application) => void): void;
  };
}

export async function setupVectorTables(appkit: AppKitWithLakebase) {
  try {
    await appkit.lakebase.query("CREATE EXTENSION IF NOT EXISTS vector");
  } catch (err: unknown) {
    const code = (err as { code?: string }).code;
    if (code === "42501") {
      console.log("[vectors] Skipping extension creation — insufficient privileges (likely already exists)");
    } else {
      throw err;
    }
  }
  await appkit.lakebase.query(`CREATE SCHEMA IF NOT EXISTS vectors`);
  const { rows } = await appkit.lakebase.query(
    `SELECT 1 FROM information_schema.tables
     WHERE table_schema = 'vectors' AND table_name = 'documents'`,
  );
  if (rows.length > 0) return;
  await appkit.lakebase.query(`
    CREATE TABLE IF NOT EXISTS vectors.documents (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      content TEXT NOT NULL,
      embedding VECTOR(1024),
      metadata JSONB NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
}

export async function insertDocument(
  appkit: AppKitWithLakebase,
  input: { content: string; embedding: number[]; metadata?: Record<string, unknown> },
) {
  const result = await appkit.lakebase.query(
    `INSERT INTO vectors.documents (content, embedding, metadata)
     VALUES ($1, $2::vector, $3)
     RETURNING id, content, metadata, created_at`,
    [input.content, JSON.stringify(input.embedding), JSON.stringify(input.metadata ?? {})],
  );
  return result.rows[0];
}

export async function retrieveSimilar(
  appkit: AppKitWithLakebase,
  queryEmbedding: number[],
  limit = 5,
) {
  const result = await appkit.lakebase.query(
    `SELECT id, content, metadata, 1 - (embedding <=> $1::vector) AS similarity
     FROM vectors.documents
     WHERE embedding IS NOT NULL
     ORDER BY embedding <=> $1::vector
     LIMIT $2`,
    [JSON.stringify(queryEmbedding), limit],
  );
  return result.rows;
}
```

Call `setupVectorTables(appkit)` from `onPluginsReady` before starting the server.

## Distance Operators

| Operator | Distance | Use for |
|----------|----------|---------|
| `<=>` | Cosine | Text similarity (default) |
| `<->` | L2 (Euclidean) | Spatial data |
| `<#>` | Negative inner product | Normalized embeddings (smaller = more similar) |

Similarity score: `1 - (embedding <=> $1::vector) AS similarity` (0 = unrelated, 1 = identical).

## Indexing

Add an index **after** inserting initial data (IVFFlat needs representative data to build):

```sql
CREATE INDEX IF NOT EXISTS idx_documents_embedding
  ON vectors.documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
ANALYZE vectors.documents;
```

For higher recall without tuning, use HNSW instead: `USING hnsw (embedding vector_cosine_ops)`.

## Cross-references

- For generating embeddings, see the `databricks-apps` skill's [model-serving.md](../../databricks-apps/references/appkit/model-serving.md) → Embeddings Pattern
- For Lakebase connection patterns, see [connectivity.md](connectivity.md)
