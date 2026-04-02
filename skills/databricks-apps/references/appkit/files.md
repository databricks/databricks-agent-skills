# Files: Unity Catalog Volume Operations

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

The plugin auto-discovers `DATABRICKS_VOLUME_*` environment variables at startup. The env var suffix becomes the volume key (lowercased). Empty values or bare `DATABRICKS_VOLUME_` prefixes are skipped.

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

## Volume Configuration

```typescript
files({
  maxUploadSize: 5_000_000_000, // 5 GB default
  customContentTypes: { ".avro": "application/avro" },
  volumes: {
    uploads: { maxUploadSize: 100_000_000 }, // 100 MB limit for this volume
    exports: {}, // uses plugin-level defaults
  },
});
```

**Merge semantics:** Auto-discovered volumes (from env vars) merge with explicitly configured ones. Explicit configuration takes precedence for per-volume overrides.

### Custom Content Types

```typescript
files({
  volumes: { data: {} },
  customContentTypes: {
    ".avro": "application/avro",
    ".ndjson": "application/x-ndjson",
  },
});
```

> ⚠️ **Blocked MIME types:** `text/html`, `text/javascript`, `application/javascript`, `application/xhtml+xml`, `image/svg+xml` are blocked to prevent stored-XSS when served inline via `/raw`.

### Configuration Types

```typescript
interface IFilesConfig {
  /** Named volumes to expose. Each key becomes a volume accessor. */
  volumes?: Record<string, VolumeConfig>;
  /** Operation timeout in milliseconds. Overrides per-tier defaults. */
  timeout?: number;
  /** Map of file extensions to MIME types (priority over built-in map). */
  customContentTypes?: Record<string, string>;
  /** Maximum upload size in bytes. Defaults to 5 GB. */
  maxUploadSize?: number;
}

interface VolumeConfig {
  /** Maximum upload size in bytes for this volume. */
  maxUploadSize?: number;
  /** Map of file extensions to MIME types for this volume. */
  customContentTypes?: Record<string, string>;
}
```

## Server-Side API (Programmatic)

Access volumes through the `files()` callable, which returns a `VolumeHandle`:

```typescript
// ✅ CORRECT — OBO access (recommended)
const entries = await appkit.files("uploads").asUser(req).list();
const content = await appkit.files("exports").asUser(req).read("report.csv");

// ❌ BLOCKED — Service principal access is not allowed
const entries = await appkit.files("uploads").list();
```

**ALWAYS use `.asUser(req)`** — direct calls without user context are blocked and will throw an error.

### VolumeAPI Methods

| Method | Signature | Returns |
| --- | --- | --- |
| `list` | `(directoryPath?: string)` | `DirectoryEntry[]` |
| `read` | `(filePath: string, options?: { maxSize?: number })` | `string` |
| `download` | `(filePath: string)` | `DownloadResponse` |
| `exists` | `(filePath: string)` | `boolean` |
| `metadata` | `(filePath: string)` | `FileMetadata` |
| `upload` | `(filePath: string, contents: ReadableStream \| Buffer \| string, options?: { overwrite?: boolean })` | `void` |
| `createDirectory` | `(directoryPath: string)` | `void` |
| `delete` | `(filePath: string)` | `void` |
| `preview` | `(filePath: string)` | `FilePreview` |

**`read()` loads entire files into memory.** Files larger than 10 MB are rejected by default — use `download()` for large files or pass `{ maxSize: <bytes> }` to override.

### Types

```typescript
interface FileMetadata {
  contentLength: number | undefined;
  contentType: string | undefined;
  lastModified: string | undefined; // ISO 8601
}

interface FilePreview extends FileMetadata {
  textPreview: string | null;  // first portion of text content, null for non-text
  isText: boolean;
  isImage: boolean;
}
```

## HTTP Routes

Routes mount at `/api/files/*`. All routes except `/volumes` execute in user context via `asUser(req)`.

| Method | Path | Query/Body | Response |
| --- | --- | --- | --- |
| GET | `/volumes` | — | `{ volumes: string[] }` |
| GET | `/:volumeKey/list` | `?path` (optional) | `DirectoryEntry[]` |
| GET | `/:volumeKey/read` | `?path` (required) | `text/plain` body |
| GET | `/:volumeKey/download` | `?path` (required) | Binary stream (attachment) |
| GET | `/:volumeKey/raw` | `?path` (required) | Binary stream (inline/attachment) |
| GET | `/:volumeKey/exists` | `?path` (required) | `{ exists: boolean }` |
| GET | `/:volumeKey/metadata` | `?path` (required) | `FileMetadata` |
| GET | `/:volumeKey/preview` | `?path` (required) | `FilePreview` |
| POST | `/:volumeKey/upload` | `?path` (required), raw body | `{ success: true }` |
| POST | `/:volumeKey/mkdir` | `body.path` (required) | `{ success: true }` |
| DELETE | `/:volumeKey` | `?path` (required) | `{ success: true }` |

Unknown volume keys return 404 with available volumes listed.

### Path Validation

All path parameters enforce:
- Required (non-empty)
- Maximum 4096 characters
- No null bytes
- No path traversal (`../` rejected)

## Frontend Components

Import file browser components from `@databricks/appkit-ui/react`:

```typescript
import {
  DirectoryList,
  FileBreadcrumb,
  FilePreviewPanel,
  NewFolderInput,
} from "@databricks/appkit-ui/react";
```

### File Browser Example

```typescript
import type { DirectoryEntry, FilePreview } from '@databricks/appkit-ui/react';
import {
  Button,
  DirectoryList,
  FileBreadcrumb,
  FilePreviewPanel,
  NewFolderInput,
} from '@databricks/appkit-ui/react';
import { useCallback, useEffect, useState } from 'react';

export function FilesPage() {
  const [volumeKey, setVolumeKey] = useState('uploads');
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
                .then((r) => r.json())
                .then(setPreview);
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
          window.open(apiUrl('download', { path }), '_blank')
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

## Execution Defaults

| Tier | Cache | Retry | Timeout | Operations |
| --- | --- | --- | --- | --- |
| Read | 60 s | 3x | 30 s | list, read, exists, metadata, preview |
| Download | none | 3x | 30 s | download, raw |
| Write | none | none | 600 s | upload, mkdir, delete |

Retry uses exponential backoff with 1 s initial delay. Download timeout applies to stream start, not full transfer.

Write operations automatically invalidate the cached `list` entry for the affected directory's parent.

## Path Resolution

Paths can be **absolute** or **relative**:

- **Absolute:** Must start with `/Volumes/` (e.g., `/Volumes/catalog/schema/vol/data.csv`)
- **Relative:** Prepended with the volume path from the environment variable (e.g., `data.csv` → `/Volumes/catalog/schema/uploads/data.csv`)

`list()` with no arguments lists the volume root.

**DO NOT use `../` in paths** — path traversal is rejected.

## Resource Requirements

Each volume key generates a required resource with `WRITE_VOLUME` permission and a `DATABRICKS_VOLUME_{KEY_UPPERCASE}` environment variable. These are declared dynamically — no explicit `volumes` config needed if env vars are set.

## Error Responses

All errors return JSON with `{ "error": "message", "plugin": "files" }`.

| Status | Description |
| --- | --- |
| 400 | Missing or invalid `path` parameter |
| 404 | Unknown volume key (response lists available volumes) |
| 413 | Upload exceeds `maxUploadSize` |
| 500 | Operation failed (SDK, network, or upstream error) |

## Troubleshooting

| Error | Cause | Solution |
| --- | --- | --- |
| `Unknown volume key "X"` | Volume env var not set or misspelled | Check `DATABRICKS_VOLUME_X` is set in `app.yaml` or `.env` |
| 413 on upload | File exceeds `maxUploadSize` | Increase `maxUploadSize` in plugin config or per-volume config |
| `read()` rejects large file | File > 10 MB default limit | Use `download()` for large files or pass `{ maxSize: <bytes> }` |
| Blocked content type on `/raw` | Dangerous MIME type (html, js, svg) | Use `/download` instead — these types are forced to attachment |
| Service principal access blocked | Called volume method without `.asUser(req)` | Always use `appkit.files("key").asUser(req).method()` |
| `path traversal` error | Path contains `../` | Use relative paths from volume root or absolute `/Volumes/...` paths |
