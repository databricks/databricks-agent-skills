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
    user_data: { auth: "on-behalf-of-user" }, // SDK calls run as end user
    exports: {}, // inherits plugin-level
  },
});
```

`auth` resolves per volume: `VolumeConfig.auth` > plugin-level `auth` > `"service-principal"`. Auto-discovered volumes merge with explicit config — `volumes: {}` is only needed for overrides.

## Permission Model

Three layers gate file access — understand all three before deploying:

1. **Unity Catalog grants** — SP volumes need the SP to hold `WRITE_VOLUME`; OBO volumes need the end user to hold it. Set at deploy time via `app.yaml` resource bindings.
2. **Execution identity** — set by the volume's `auth` field. `"service-principal"` (default) runs SDK calls as the SP. `"on-behalf-of-user"` runs them as the request's end user via `runInUserContext`, using the `x-forwarded-access-token` header injected by the Databricks Apps reverse proxy. Programmatic `asUser(req)` is a hard override that forces OBO regardless of the volume's `auth`.
3. **File policies** — per-volume function `(action, resource, user) → boolean` evaluated **before** every operation, on every code path (HTTP and programmatic, SP and OBO).

> On SP volumes, UC grants gate the SP — removing a user's UC grant has no effect on HTTP access, so policies are the only per-user gate. On OBO volumes, UC grants gate the end user directly, and policies stack on top.

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

Built-in policies:

| Helper                      | Allows                                                             |
| --------------------------- | ------------------------------------------------------------------ |
| `files.policy.publicRead()` | `list`, `read`, `download`, `raw`, `exists`, `metadata`, `preview` |
| `files.policy.allowAll()`   | every action                                                       |
| `files.policy.denyAll()`    | no action (yes — even `list`)                                      |

Combinators: `policy.all(...)` (AND, short-circuits on deny), `policy.any(...)` (OR, short-circuits on allow), `policy.not(p)` (e.g. `not(publicRead())` = write-only drop-box).

A `FilePolicy` is `(action, resource, user) => boolean | Promise<boolean>`. Exported `READ_ACTIONS` / `WRITE_ACTIONS` are `ReadonlySet<FileAction>` for action-class checks. `user.id` comes from the `x-forwarded-user` header (HTTP) or `req` (`asUser(req)`); `user.isServicePrincipal === true` when the programmatic API skipped `asUser()`. Full `FileAction` / `FileResource` / `FilePolicyUser` shape: `npx @databricks/appkit docs Files plugin`.

```typescript
import { type FilePolicy, WRITE_ACTIONS } from "@databricks/appkit";

const ADMIN_IDS = ["admin@company.com"];

// Writes admin-only; reads open. Wrap with `policy.any(spBypass, adminWrite)` for SP bypass.
const adminWrite: FilePolicy = (action, _resource, user) => {
  if (WRITE_ACTIONS.has(action)) return ADMIN_IDS.includes(user.id);
  return true;
};

files({ volumes: { reports: { policy: adminWrite } } });
```

**Enforcement**: HTTP denial → `403 { error: "Policy denied \"{action}\" on volume \"{volume}\"", plugin: "files" }`. Programmatic denial → throws `PolicyDeniedError` (exported from `@databricks/appkit`, has `.action` / `.volumeKey`). Both SP and `asUser(req)` calls are gated.

## Server-Side API (Programmatic)

Access volumes through the `files()` callable, which returns a `VolumeHandle`. Without `asUser(req)`, calls follow the volume's `auth` setting (SP by default). With `asUser(req)`, the call is wrapped in `runInUserContext` — the SDK call runs as the request's end user **and** the policy sees that user, regardless of the volume's `auth`.

```typescript
// Forced OBO. SDK call runs as user; policy sees user.id from req.
await appkit.files("uploads").asUser(req).list();

// Follows the volume's auth. On SP volumes: runs as SP, policy sees isServicePrincipal: true.
await appkit.files("uploads").list();

// Named accessor equivalent.
await appkit.files.volume("uploads").asUser(req).list();
```

**Use `.asUser(req)` in user-driven route handlers** when you want UC grants enforced against the actual user. In production, `asUser(req)` throws `AuthenticationError.missingToken` if the `x-forwarded-user` header is missing; in dev (`NODE_ENV === "development"`) it logs a warning and falls back to SP. Policy denial throws `PolicyDeniedError`.

**`VolumeAPI` methods**: `list`, `read`, `download`, `exists`, `metadata`, `preview`, `upload`, `createDirectory`, `delete`. `read()` caps files at 10 MB by default — pass `{ maxSize: <bytes> }` or use `download()` for larger files. Paths are absolute (`/Volumes/...`) or relative to the volume root; `../` and null bytes are rejected. Reads cache 60 s with 3 retries; writes have a 600 s timeout, no retry, no cache; cache keys include the volume key, and writes auto-invalidate the parent directory's `list` cache. Full method signatures: `npx @databricks/appkit docs Files plugin`.

## HTTP Routes

Mounted at `/api/files/*`. Execution identity follows the volume's `auth` field: SP volumes run SDK calls as the service principal; OBO volumes run them as the end user using the token from `x-forwarded-access-token`. User identity (from `x-forwarded-user`) is always passed to the volume's policy (denial → `403`). Reads are GET (`list`, `read`, `download`, `raw`, `exists`, `metadata`, `preview`); writes are POST (`upload`, `mkdir`) and DELETE — full route shape, request bodies, and response types: `npx @databricks/appkit docs Files plugin`.

The `/raw` endpoint sets `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox`. Inline streaming uses an allowlist (images, plain text, CSV, markdown, JSON, PDF); anything else is forced to attachment.

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
      user_api_scopes:
        - files.files        # Needed when using .asUser(req) programmatic API
      resources:
        - name: uploads-volume
          volume:
            path: /Volumes/catalog/schema/uploads
            permission: WRITE_VOLUME
```

> **Note:** `user_api_scopes` is required for OBO volumes (`auth: "on-behalf-of-user"`) and for any `appkit.files("key").asUser(req)` programmatic call. Pure SP volumes accessed only via HTTP routes don't need it.

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
