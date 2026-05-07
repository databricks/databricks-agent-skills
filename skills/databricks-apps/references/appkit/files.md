# Files: Unity Catalog Volume Operations

**For full Files plugin API (routes, types, config options)**: run `npx @databricks/appkit docs` → Files plugin.

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

### Configuration

Plugin-level options inherit to every volume; per-volume config overrides them:

```typescript
files({
  maxUploadSize: 5_000_000_000, // 5 GB default (all volumes)
  customContentTypes: { ".avro": "application/avro" },
  volumes: {
    uploads: { maxUploadSize: 100_000_000 }, // 100 MB override
    exports: {}, // inherits plugin-level
  },
});
```

Auto-discovered volumes merge with explicit config — `volumes: {}` is only needed for overrides.

## Permission Model

Three layers gate file access — understand all three before deploying:

1. **Unity Catalog grants** — the SP needs `WRITE_VOLUME`. Set at deploy time via `app.yaml` resource bindings; the plugin auto-declares the requirement.
2. **Execution identity** — HTTP routes **always** run as the service principal. The programmatic API runs as SP by default; `asUser(req)` re-wraps with the request's user identity.
3. **File policies** — per-volume function `(action, resource, user) → boolean` evaluated **before** every operation. This is the only layer that distinguishes between users on HTTP routes (since HTTP always uses SP credentials).

> Removing a user's UC `WRITE_VOLUME` grant has **no effect on HTTP access** — the SP's grant is what's used. Policies are the only way to restrict per-user access through HTTP routes.

## Access Policies

Volumes without an explicit `policy` default to `files.policy.publicRead()` (reads allowed, writes denied) and log a startup warning. Set an explicit policy on every volume that needs writes.

```typescript
import { files } from "@databricks/appkit";

files({
  volumes: {
    public_data: { policy: files.policy.publicRead() }, // reads only
    uploads: { policy: files.policy.allowAll() }, // anyone can write
    archive: { policy: files.policy.denyAll() }, // locked down
  },
});
```

### Built-in policies

| Helper                      | Allows                                                             |
| --------------------------- | ------------------------------------------------------------------ |
| `files.policy.publicRead()` | `list`, `read`, `download`, `raw`, `exists`, `metadata`, `preview` |
| `files.policy.allowAll()`   | every action                                                       |
| `files.policy.denyAll()`    | no action (yes — even `list`)                                      |

### Combinators

- `files.policy.all(p1, p2, ...)` — AND, short-circuits on first deny
- `files.policy.any(p1, p2, ...)` — OR, short-circuits on first allow
- `files.policy.not(p)` — invert (e.g. `not(publicRead())` = write-only drop-box)

### Custom policies

A `FilePolicy` is `(action, resource, user) => boolean | Promise<boolean>`. `READ_ACTIONS` and `WRITE_ACTIONS` are exported `Set<FileAction>` for action-class checks.

```typescript
import { type FilePolicy, WRITE_ACTIONS } from "@databricks/appkit";

const ADMIN_IDS = ["admin@company.com"];

const adminWrite: FilePolicy = (action, _resource, user) => {
  if (WRITE_ACTIONS.has(action)) return ADMIN_IDS.includes(user.id);
  return true; // reads open to everyone
};

files({
  volumes: { reports: { policy: adminWrite } },
});
```

Mix custom logic with built-ins via combinators — e.g. SP can do anything, users can only read:

```typescript
files.policy.any(
  (_action, _resource, user) => !!user.isServicePrincipal,
  files.policy.publicRead(),
);
```

### Policy inputs

```typescript
type FileAction =
  | "list" | "read" | "download" | "raw" | "exists" | "metadata" | "preview"
  | "upload" | "mkdir" | "delete";

interface FileResource {
  path: string;     // relative path within the volume
  volume: string;   // volume key
  size?: number;    // content-length in bytes (uploads only)
}

interface FilePolicyUser {
  id: string;                    // from `x-forwarded-user` header (HTTP) or req
  isServicePrincipal?: boolean;  // true when programmatic API skipped asUser()
}
```

### Enforcement

- **HTTP routes**: denied → `403 { error: "Policy denied \"{action}\" on volume \"{volume}\"", plugin: "files" }`.
- **Programmatic API**: denied → throws `PolicyDeniedError` (importable from `@databricks/appkit`) with `.action` and `.volumeKey` properties. Both `appkit.files("vol").list()` (SP, `isServicePrincipal: true`) and `appkit.files("vol").asUser(req).list()` (user) are gated.

## Server-Side API (Programmatic)

Access volumes through the `files()` callable, which returns a `VolumeHandle`. Every method runs as the service principal — `asUser(req)` only changes the user identity passed into the **policy** check (the underlying SDK call still uses SP credentials).

```typescript
// User identity passed to policy → user.id from req
await appkit.files("uploads").asUser(req).list();

// SP identity passed to policy → user.isServicePrincipal === true; logs a warning
await appkit.files("uploads").list();

// Named accessor equivalent
await appkit.files.volume("uploads").asUser(req).list();
```

**Use `.asUser(req)` in route handlers.** Without it the policy sees `isServicePrincipal: true` and a warning is logged — fine for background jobs, wrong for user-driven endpoints where per-user policy decisions matter. Policy denial throws `PolicyDeniedError`.

**`VolumeAPI` methods**: `list`, `read`, `download`, `exists`, `metadata`, `preview`, `upload`, `createDirectory`, `delete`. `read()` caps files at 10 MB by default — pass `{ maxSize: <bytes> }` or use `download()` for larger files. Paths are absolute (`/Volumes/...`) or relative to the volume root; `../` and null bytes are rejected.

### Execution defaults

Every operation runs through cache/retry/timeout interceptors:

| Tier     | Operations                            | Cache | Retry | Timeout |
| -------- | ------------------------------------- | ----- | ----- | ------- |
| Read     | list, read, exists, metadata, preview | 60 s  | 3×    | 30 s    |
| Download | download, raw                         | —     | 3×    | 30 s    |
| Write    | upload, mkdir, delete                 | —     | —     | 600 s   |

Cache keys include the volume key (no cross-volume collisions). Write operations auto-invalidate the parent directory's cached `list` entry.

## HTTP Routes

Mounted at `/api/files/*`. All routes execute as the service principal; user identity is read from the `x-forwarded-user` header and passed to the volume's policy. Policy denial → `403`.

| Method | Path                         | Purpose                                    |
| ------ | ---------------------------- | ------------------------------------------ |
| GET    | `/volumes`                   | List configured volume keys                |
| GET    | `/:volumeKey/list?path=`     | Directory listing                          |
| GET    | `/:volumeKey/read?path=`     | Read text content                          |
| GET    | `/:volumeKey/download?path=` | Binary stream (attachment)                 |
| GET    | `/:volumeKey/raw?path=`      | Inline stream (attachment for unsafe MIME) |
| GET    | `/:volumeKey/exists?path=`   | Existence check                            |
| GET    | `/:volumeKey/metadata?path=` | File metadata                              |
| GET    | `/:volumeKey/preview?path=`  | Preview (text + type flags)                |
| POST   | `/:volumeKey/upload?path=`   | Upload (raw body)                          |
| POST   | `/:volumeKey/mkdir`          | Create directory (`body.path`)             |
| DELETE | `/:volumeKey?path=`          | Delete file                                |

Path validation: non-empty, ≤ 4096 chars, no null bytes, no `../`. The `/raw` endpoint sets `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox`; HTML/JS/SVG MIME types are forced to attachment.

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

The plugin **auto-generates** volume resource requirements from `DATABRICKS_VOLUME_*` env vars — setting them in `app.yaml` is usually all you need. Each discovered volume key becomes a required `WRITE_VOLUME` resource validated at startup.

Declare the volume explicitly in `databricks.yml` only when you need to pin it as a managed resource, then wire the env var via `valueFrom` in `app.yaml`:

```yaml
# databricks.yml
resources:
  apps:
    my_app:
      resources:
        - name: uploads-volume
          volume:
            path: /Volumes/catalog/schema/uploads
            permission: WRITE_VOLUME
```

```yaml
# app.yaml
env:
  - name: DATABRICKS_VOLUME_UPLOADS
    valueFrom: uploads-volume
```

## Troubleshooting

| Error                                      | Cause                                                                              | Solution                                                                                  |
| ------------------------------------------ | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `Unknown volume key "X"`                   | Volume env var not set or misspelled                                               | Check `DATABRICKS_VOLUME_X` is set in `app.yaml` or `.env`                                |
| 413 on upload                              | File exceeds `maxUploadSize`                                                       | Increase `maxUploadSize` in plugin config or per-volume config                            |
| `read()` rejects large file                | File > 10 MB default limit                                                         | Use `download()` for large files or pass `{ maxSize: <bytes> }`                           |
| Blocked content type on `/raw`             | Dangerous MIME type (html, js, svg)                                                | Use `/download` instead — these types are forced to attachment                            |
| 403 on HTTP route                          | Volume's policy denied the action for the requesting user                          | Inspect `policy` config; user id comes from the `x-forwarded-user` header                 |
| Writes return 403 unexpectedly             | Volume has no `policy` configured → defaults to `publicRead()` which denies writes | Set explicit `policy: files.policy.allowAll()` (or stricter) on volumes that accept writes |
| `PolicyDeniedError` from programmatic call | Volume's policy denied the action — SP identity used if `asUser(req)` was omitted  | Call `.asUser(req)` for user-driven calls; gate trusted SP code with `policy.allowAll()` |
| Invalid path error                         | Path contains `../`, null bytes, or exceeds 4096 chars                             | Use relative paths from the volume root, or absolute `/Volumes/...` paths                 |
