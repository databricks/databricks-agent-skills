# Files: Unity Catalog Volume Operations

**For full Files plugin API (routes, types, config options)**: run `npx @databricks/appkit docs ./docs/plugins/files.md`.

Use the `files()` plugin when your app needs to **browse, upload, download, or manage files** in Databricks Unity Catalog Volumes. For analytics dashboards reading from a SQL warehouse, use `config/queries/` instead. For persistent CRUD storage, use Lakebase.

## When to Use Files vs Other Patterns

| Pattern           | Use Case                                    | Data Source              |
| ----------------- | ------------------------------------------- | ------------------------ |
| Analytics         | Read-only dashboards, charts, KPIs          | Databricks SQL Warehouse |
| Lakebase          | CRUD operations, persistent state, forms    | PostgreSQL (Lakebase)    |
| Files             | File uploads, downloads, browsing, previews | Unity Catalog Volumes    |
| Files + Analytics | Upload CSVs then query warehouse tables     | Volumes + SQL Warehouse  |

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
  plugins: [server(), files()],
});
```

### Configuration Overrides

Only add plugin config when you need to override defaults from the discovered `DATABRICKS_VOLUME_*` env vars:

```typescript
files({
  maxUploadSize: 5_000_000_000, // plugin-level default
  volumes: {
    uploads: {
      maxUploadSize: 100_000_000,
      policy: files.policy.allowAll(), // required for writes
    },
    user_data: {
      auth: "on-behalf-of-user", // HTTP routes run SDK calls as end user
    },
  },
});
```

Auto-discovered volumes merge with explicit config, so `volumes: {}` is only needed for overrides. Check the AppKit docs for the current `IFilesConfig` / `VolumeConfig` shape.

## Permission Model

Three layers gate file access:

1. **Unity Catalog grants** — service-principal volumes need the app SP to hold `WRITE_VOLUME`; OBO volumes need each end user to hold it.
2. **Execution identity** — HTTP routes use the volume's `auth` mode. Programmatic user-driven handlers must call `.asUser(req)` to run SDK calls as the request user.
3. **File policies** — app-level allow/deny functions evaluated before every operation.

For SP volumes, removing a user's UC grant has no effect on HTTP access because the SDK call uses the SP. Use policies for per-user restrictions. For OBO volumes, UC grants gate the end user and policies stack on top.

## Access Policies

Volumes without an explicit `policy` default to `files.policy.publicRead()` (reads allowed, writes denied) and log a startup warning. Set an explicit policy on every volume that accepts uploads, directory creation, or deletes.

```typescript
import { files } from "@databricks/appkit";

files({
  volumes: {
    public_data: { policy: files.policy.publicRead() },
    uploads: { policy: files.policy.allowAll() },
    archive: { policy: files.policy.denyAll() },
  },
});
```

Use custom policies when access depends on the requesting user or action. For exact built-ins, combinators, `FileAction`, `FileResource`, `FilePolicyUser`, and `PolicyDeniedError` behavior, check `npx @databricks/appkit docs ./docs/plugins/files.md`.

## Server-Side API (Programmatic)

Access volumes through the `files()` callable, which returns a `VolumeHandle`. Direct programmatic calls do not have request headers available, so they normally run as the service principal. Use `.asUser(req)` in user-driven route handlers when the SDK call must run as the request user.

```typescript
// User-driven handler: SDK call runs as user; policy sees user.id from req.
await appkit.files("uploads").asUser(req).list();

// Background or trusted server code: runs as SP.
await appkit.files("uploads").list();
```

**Use `.asUser(req)` in user-driven route handlers** when you want UC grants enforced against the actual user. In production, `asUser(req)` throws `AuthenticationError.missingToken` if the forwarded user or access-token header is missing; in dev (`NODE_ENV === "development"`) it logs a warning and falls back to SP. Policy denial throws `PolicyDeniedError`.

For method signatures, path rules, cache behavior, and retry/timeout defaults, check `npx @databricks/appkit docs ./docs/plugins/files.md`.

## HTTP Routes

Mounted at `/api/files/*`. Routes use the volume's `auth` mode and run the policy before the operation. Use the AppKit docs for the exact route list, request bodies, response types, and `/raw` content-security behavior.

## Frontend Components

Import file browser components from `@databricks/appkit-ui/react`. Full component props: `npx @databricks/appkit docs ./docs/api/appkit-ui/files/DirectoryList.md` and the related component pages.

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
  const response = await fetch(apiUrl("upload", { path: uploadPath }), {
    method: "POST",
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
    { method: "DELETE" },
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
  const response = await fetch(apiUrl("mkdir"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: dirPath }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      data.error ?? `Create directory failed (${response.status})`,
    );
  }
};
```

## Resource Requirements

The plugin auto-generates volume resource requirements from `DATABRICKS_VOLUME_*` env vars. Setting them in `app.yaml` is usually all you need.

Declare the volume explicitly in `databricks.yml` only when you need to pin it as a managed resource, then wire the env var via `valueFrom` in `app.yaml`:

```yaml
# databricks.yml
resources:
  apps:
    my_app:
      user_api_scopes:
        - files.files        # Needed when using .asUser(req) programmatic API
      resources:
        - name: uploads-volume
          volume:
            path: /Volumes/catalog/schema/uploads
            permission: WRITE_VOLUME
```

> **Note:** `user_api_scopes` is required for OBO volumes (`auth: "on-behalf-of-user"`) and for any `appkit.files("key").asUser(req)` programmatic call. Pure SP volumes accessed only via HTTP routes don't need it. The plugin docs have the latest resource-requirement behavior.

```yaml
# app.yaml
env:
  - name: DATABRICKS_VOLUME_UPLOADS
    valueFrom: uploads-volume
```

## Troubleshooting

| Error                                      | Cause                                                                              | Solution                                                                                  |
| ------------------------------------------ | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `Unknown volume "X"`                       | Volume env var not set or misspelled                                               | Check `DATABRICKS_VOLUME_X` is set in `app.yaml` or `.env`                                |
| 413 on upload                              | File exceeds `maxUploadSize`                                                       | Increase `maxUploadSize` in plugin config or per-volume config                            |
| `read()` rejects large file                | File > 10 MB default limit                                                         | Use `download()` for large files or pass `{ maxSize: <bytes> }`                           |
| Blocked content type on `/raw`             | Dangerous MIME type (html, js, svg)                                                | Use `/download` instead — these types are forced to attachment                            |
| 403 on HTTP route                          | Volume's policy denied the action for the requesting user                          | Inspect `policy` config; user id comes from the `x-forwarded-user` header                 |
| Writes return 403 unexpectedly             | Volume has no `policy` configured → defaults to `publicRead()` which denies writes | Set explicit `policy: files.policy.allowAll()` (or stricter) on volumes that accept writes |
| `PolicyDeniedError` from programmatic call | Volume's policy denied the action — SP identity used if `asUser(req)` was omitted  | Call `.asUser(req)` for user-driven calls; gate trusted SP code with `policy.allowAll()` |
| Invalid path error                         | Path contains `../`, null bytes, or exceeds 4096 chars                             | Use relative paths from the volume root, or absolute `/Volumes/...` paths                 |
