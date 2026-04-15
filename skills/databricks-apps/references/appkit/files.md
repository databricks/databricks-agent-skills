# Files: Unity Catalog Volume Operations

**For full Files plugin API (routes, types, config options)**: run `npx @databricks/appkit docs` → Files plugin.

Use the `files()` plugin when your app needs to **browse, upload, download, or manage files** in Databricks Unity Catalog Volumes. For analytics dashboards reading from a SQL warehouse, use `config/queries/` instead. For persistent CRUD storage, use Lakebase.

## When to Use Files vs Other Patterns

| Pattern | Use Case | Data Source |
| --- | --- | --- |
| Analytics | Read-only dashboards, charts, KPIs | Databricks SQL Warehouse |
| Lakebase | CRUD operations, persistent state, forms | PostgreSQL (Lakebase) |
| Files | File uploads, downloads, browsing, previews | Unity Catalog Volumes |
| Files + Analytics | Upload CSVs then query warehouse tables | Volumes + SQL Warehouse |

## Scaffolding

```bash
databricks apps init --name <NAME> --features files \
  --run none --profile <PROFILE>
```

**Files + analytics:**

```bash
databricks apps init --name <NAME> --features analytics,files \
  --set "analytics.sql-warehouse.id=<WAREHOUSE_ID>" \
  --run none --profile <PROFILE>
```

Configure volume paths via environment variables in `app.yaml` or `.env`:

```
DATABRICKS_VOLUME_UPLOADS=/Volumes/catalog/schema/uploads
DATABRICKS_VOLUME_EXPORTS=/Volumes/catalog/schema/exports
```

The env var suffix (after `DATABRICKS_VOLUME_`) becomes the volume key, lowercased.

## Plugin Setup

```typescript
import { createApp, files, server } from "@databricks/appkit";

await createApp({
  plugins: [
    server(),
    files(),
  ],
});
```

## Server-Side API (Programmatic)

Access volumes through the `files()` callable, which returns a `VolumeHandle`:

```typescript
// ✅ CORRECT — OBO access (recommended)
const entries = await appkit.files("uploads").asUser(req).list();
const content = await appkit.files("exports").asUser(req).read("report.csv");

// ❌ WRONG — omitting .asUser(req)
const entries = await appkit.files("uploads").list();
// In dev: silently falls back to service principal credentials, bypassing user-level UC permissions
// In production: throws an error
```

**ALWAYS use `.asUser(req)`** — without it, dev mode silently uses the app's service principal (masking permission issues that will crash in production).

## Frontend Components

Import file browser components from `@databricks/appkit-ui/react`. Full component props: `npx @databricks/appkit docs "FileBreadcrumb"`.

### File Browser Example

```typescript
import type { DirectoryEntry, FilePreview } from '@databricks/appkit-ui/react';
import {
  DirectoryList,
  FileBreadcrumb,
  FilePreviewPanel,
} from '@databricks/appkit-ui/react';
import { useCallback, useEffect, useState } from 'react';

export function FilesPage() {
  const [volumeKey] = useState('uploads');
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<FilePreview | null>(null);

  const apiUrl = useCallback(
    (action: string, params?: Record<string, string>) => {
      const base = `/api/files/${volumeKey}/${action}`;
      if (!params) return base;
      return `${base}?${new URLSearchParams(params).toString()}`;
    },
    [volumeKey],
  );

  const loadDirectory = useCallback(async (path?: string) => {
    const url = path ? apiUrl('list', { path }) : apiUrl('list');
    const res = await fetch(url);
    if (!res.ok) {
      const errBody = await res.json().catch(() => null);
      console.error('Failed to load directory', errBody ?? res.statusText);
      return;
    }
    const data: DirectoryEntry[] = await res.json();
    // Sort: directories first, then alphabetically
    data.sort((a, b) => {
      if (a.is_directory && !b.is_directory) return -1;
      if (!a.is_directory && b.is_directory) return 1;
      return (a.name ?? '').localeCompare(b.name ?? '');
    });
    setEntries(data);
    setCurrentPath(path ?? '');
  }, [apiUrl]);

  useEffect(() => { loadDirectory(); }, [loadDirectory]);

  const segments = currentPath.split('/').filter(Boolean);

  return (
    <div className="flex gap-6">
      <div className="flex-2 min-w-0">
        <FileBreadcrumb
          rootLabel={volumeKey}
          segments={segments}
          onNavigateToRoot={() => loadDirectory()}
          onNavigateToSegment={(i) =>
            loadDirectory(segments.slice(0, i + 1).join('/'))
          }
        />
        <DirectoryList
          entries={entries}
          onEntryClick={(entry) => {
            const entryPath = currentPath
              ? `${currentPath}/${entry.name}`
              : entry.name ?? '';
            if (entry.is_directory) {
              loadDirectory(entryPath);
            } else {
              setSelectedFile(entryPath);
              fetch(apiUrl('preview', { path: entryPath }))
                .then(async (r) => {
                  if (!r.ok) {
                    const errBody = await r.json().catch(() => null);
                    console.error('Failed to load file preview', errBody ?? r.statusText);
                    return null;
                  }
                  return r.json();
                })
                .then((data) => {
                  if (data) {
                    setPreview(data);
                  }
                });
            }
          }}
          resolveEntryPath={(entry) =>
            currentPath ? `${currentPath}/${entry.name}` : entry.name ?? ''
          }
          isAtRoot={!currentPath}
          selectedPath={selectedFile}
        />
      </div>
      <FilePreviewPanel
        className="flex-1 min-w-0"
        selectedFile={selectedFile}
        preview={preview}
        onDownload={(path) =>
          window.open(apiUrl('download', { path }), '_blank', 'noopener,noreferrer')
        }
        imagePreviewSrc={(p) => apiUrl('raw', { path: p })}
      />
    </div>
  );
}
```

### Upload Pattern

```typescript
const handleUpload = async (file: File) => {
  const uploadPath = currentPath ? `${currentPath}/${file.name}` : file.name;
  const response = await fetch(apiUrl('upload', { path: uploadPath }), {
    method: 'POST',
    body: file,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error ?? `Upload failed (${response.status})`);
  }
  // Reload directory after upload
  await loadDirectory(currentPath || undefined);
};
```

### Delete Pattern

```typescript
const handleDelete = async (filePath: string) => {
  const response = await fetch(
    `/api/files/${volumeKey}?path=${encodeURIComponent(filePath)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error ?? `Delete failed (${response.status})`);
  }
};
```

### Create Directory Pattern

```typescript
const handleCreateDirectory = async (name: string) => {
  const dirPath = currentPath ? `${currentPath}/${name}` : name;
  const response = await fetch(apiUrl('mkdir'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: dirPath }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error ?? `Create directory failed (${response.status})`);
  }
};
```

## Resource Requirements

Each volume key requires a resource with `WRITE_VOLUME` permission. Declare in `databricks.yml`:

```yaml
resources:
  apps:
    my_app:
      resources:
        - name: uploads-volume
          volume:
            path: /Volumes/catalog/schema/uploads
            permission: WRITE_VOLUME
```

Wire the env var in `app.yaml`:

```yaml
env:
  - name: DATABRICKS_VOLUME_UPLOADS
    valueFrom: uploads-volume
```

## Troubleshooting

| Error | Cause | Solution |
| --- | --- | --- |
| `Unknown volume key "X"` | Volume env var not set or misspelled | Check `DATABRICKS_VOLUME_X` is set in `app.yaml` or `.env` |
| 413 on upload | File exceeds `maxUploadSize` | Increase `maxUploadSize` in plugin config or per-volume config |
| `read()` rejects large file | File > 10 MB default limit | Use `download()` for large files or pass `{ maxSize: <bytes> }` |
| Blocked content type on `/raw` | Dangerous MIME type (html, js, svg) | Use `/download` instead — these types are forced to attachment |
| Service principal access blocked | Called volume method without `.asUser(req)` | Always use `appkit.files("key").asUser(req).method()` |
| `path traversal` error | Path contains `../` | Use relative paths from volume root or absolute `/Volumes/...` paths |
