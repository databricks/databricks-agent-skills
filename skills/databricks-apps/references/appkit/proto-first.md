# Proto-First App Design

Schema-first approach for AppKit apps using protobuf data contracts. Define contracts BEFORE implementation — derive TypeScript types, Lakebase DDL, and Volume paths from `.proto` files.

**When to use:** New apps with multiple plugins (files + lakebase + jobs), or adding typed boundaries to existing apps. Skip for quick prototypes.

**Requires:** `buf` CLI for proto linting and code generation.

**Rule: No implementation before contracts. No contracts without consumers.**

Define protobuf data contracts FIRST, then derive everything else (TypeScript types, Lakebase DDL, Volume paths, API shapes) from those contracts.

## When to Use

| Scenario | Use this skill |
|----------|---------------|
| Creating a new Databricks app | YES — define contracts before `databricks apps init` |
| Adding a new data boundary to an existing app | YES — add proto before implementation |
| Quick prototype / hackathon | NO — skip contracts, move fast |
| Modifying existing typed code | NO — contracts already exist |

## Core Principle

```
User intent → Module map → Proto contracts → Generated types → Implementation
                                  ↓                    ↓
                            Lakebase DDL        TypeScript interfaces
                                  ↓                    ↓
                            Migrations           Plugin code
```

The `.proto` file is the single source of truth. If it's not in a proto, it doesn't cross a module boundary.

## Phase 1: Decompose into Modules

Every Databricks app decomposes into a combination of these plugin modules:

| Module | Plugin | Data Boundary | Owns |
|--------|--------|---------------|------|
| **Storage** | files | UC Volumes | Blobs, uploads, artifacts, archives |
| **Database** | lakebase | Postgres tables | Structured records, queries, migrations |
| **Compute** | jobs | Databricks Jobs API | Job runs, task results, cluster configs |
| **Analytics** | analytics | SQL Warehouse | Read-only queries, dashboards |
| **Serving** | server | HTTP/tRPC routes | API endpoints, SSE streams |

### Decomposition Rules

1. **Each module owns its data** — files plugin never writes to lakebase, lakebase never writes to volumes.
2. **Cross-module communication is typed** — a proto message, never a raw JSON blob.
3. **Every proto message has exactly one producer module.**
4. **Multiple modules can consume** — but the producer defines the schema.
5. **No god messages** — if a message has >12 fields, split it.

### Output: Module Map

Before proceeding, produce a module map for the user to confirm:

```
App: <app-name>
Modules:
  storage:   files plugin    → uploads/, results/, artifacts/
  db:        lakebase plugin → runs, metrics, configs tables
  compute:   jobs            → generation tasks, eval tasks
  api:       server plugin   → POST /run, GET /status, SSE /stream
```

## Phase 2: Define Proto Contracts

### Directory Structure

```
proto/
├── buf.yaml
├── buf.gen.yaml
└── <app>/
    └── v1/
        ├── common.proto     # Shared enums, IDs
        ├── storage.proto    # Files plugin boundary
        ├── database.proto   # Lakebase plugin boundary
        ├── compute.proto    # Jobs boundary
        └── api.proto        # Server/API boundary
```

### Proto Style Rules

- **Package**: `<app>.v1` (versioned from day one)
- **One file per module boundary**, not per message
- **Every field has a consumer** — if no code reads it, delete it
- **snake_case** for all field names
- **proto3** syntax only

### Files Plugin Boundary (`storage.proto`)

The files plugin operates on UC Volumes. Type every file path and payload:

```protobuf
syntax = "proto3";
package <app>.v1;

import "google/protobuf/timestamp.proto";

// StoredArtifact — produced by files plugin after upload.
message StoredArtifact {
  string volume_path = 1;
  string content_type = 2;
  int64 size_bytes = 3;
  google.protobuf.Timestamp created_at = 4;
  string checksum_sha256 = 5;
}

// UploadRequest — sent to files plugin by api module.
message UploadRequest {
  string destination_path = 1;
  string content_type = 2;
  bytes content = 3;
  map<string, string> metadata = 4;
}

// VolumeLayout — design-time contract for volume directory structure.
message VolumeLayout {
  string root = 1;          // /Volumes/catalog/schema/app_name
  string uploads_dir = 2;   // uploads/
  string results_dir = 3;   // results/
  string artifacts_dir = 4; // artifacts/
}
```

### Lakebase Plugin Boundary (`database.proto`)

Every Lakebase table has a corresponding proto message. The message IS the schema:

```protobuf
syntax = "proto3";
package <app>.v1;

import "google/protobuf/timestamp.proto";

// RunRecord — one row in the `runs` table.
// Producer: compute module. Consumers: api, analytics.
message RunRecord {
  string run_id = 1;
  string app_name = 2;
  RunStatus status = 3;
  google.protobuf.Timestamp started_at = 4;
  google.protobuf.Timestamp completed_at = 5;
  string error_message = 6;
  string config_json = 7;
}

// MetricRecord — one row in the `metrics` table.
// Producer: compute module. Consumers: analytics, api.
message MetricRecord {
  string run_id = 1;
  string metric_name = 2;
  double value = 3;
  google.protobuf.Timestamp recorded_at = 4;
  map<string, string> dimensions = 5;
}
```

### Jobs Boundary (`compute.proto`)

Type job task inputs and outputs:

```protobuf
syntax = "proto3";
package <app>.v1;

// JobTaskInput — typed payload sent to a Databricks job task.
// Producer: api module. Consumer: job task code.
message JobTaskInput {
  string task_id = 1;
  string task_type = 2;
  string run_id = 3;
  bytes input_payload = 4;
  map<string, string> env = 5;
}

// JobTaskOutput — typed result from a completed job task.
// Producer: job task code. Consumer: api module.
message JobTaskOutput {
  string task_id = 1;
  string run_id = 2;
  bool success = 3;
  string error = 4;
  bytes output_payload = 5;
  int64 duration_ms = 6;
  map<string, string> metrics = 7;
}
```

## Phase 3: Generate Types and DDL

### 3a. Buf configuration

```yaml
# buf.yaml
version: v2
lint:
  use:
    - STANDARD
breaking:
  use:
    - FILE
```

```yaml
# buf.gen.yaml
version: v2
plugins:
  - remote: buf.build/connectrpc/es
    out: proto/gen
    opt: target=ts
```

### 3b. Generate TypeScript types

```bash
buf lint proto/
buf generate proto/
```

### 3c. Generate Lakebase DDL

For each message in `database.proto`, generate a numbered migration file.

**Proto→SQL type mapping:**

| Proto Type | SQL Type | Default |
|-----------|----------|---------|
| `string` | `TEXT` | `''` |
| `bool` | `BOOLEAN` | `false` |
| `int32` | `INTEGER` | `0` |
| `int64` | `BIGINT` | `0` |
| `double` | `DOUBLE PRECISION` | `0.0` |
| `bytes` | `BYTEA` | `NULL` |
| `Timestamp` | `TIMESTAMPTZ` | `NOW()` |
| `repeated T` | `JSONB` | `'[]'::jsonb` |
| `map<K,V>` | `JSONB` | `'{}'::jsonb` |
| nested message | `JSONB` | `NULL` |
| `enum` | `TEXT` | first value name |

Example migration:

```sql
-- migrations/001_create_runs.sql
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT NOT NULL,
  app_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'RUN_STATUS_PENDING',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  config_json JSONB,
  PRIMARY KEY (run_id, app_name)
);
```

### 3d. Validate

```bash
npx tsc --noEmit  # all generated types compile
buf lint proto/    # proto style checks
```

## Phase 4: Implement Against Contracts

NOW implementation begins. Each module uses ONLY its generated types:

```typescript
import type { StoredArtifact, UploadRequest } from '../proto/gen/<app>/v1/storage';
import type { RunRecord, MetricRecord } from '../proto/gen/<app>/v1/database';
import type { JobTaskInput, JobTaskOutput } from '../proto/gen/<app>/v1/compute';
```

No `any`, no `unknown`, no `JSON.parse()` at module boundaries.

## Validation Checklist

Before writing implementation code:

- [ ] Module map exists with clear data boundaries
- [ ] Proto files exist for every cross-boundary data structure
- [ ] `buf lint proto/` passes
- [ ] `buf generate proto/` produces TypeScript types
- [ ] Lakebase DDL derived from `database.proto` messages
- [ ] No proto message exceeds 12 fields
- [ ] Every field has at least one identified consumer
- [ ] Every message has exactly one producer module
- [ ] Volume layout documented (not freeform paths)
- [ ] Job inputs/outputs typed (no raw JSON params)

## Common Traps

| Trap | Why it fails | Fix |
|------|-------------|-----|
| "I'll add the proto later" | Boundaries calcify around untyped shapes | Proto first or not at all |
| `any` at a module boundary | Type errors surface at runtime, not compile time | Use generated types |
| `JSON.parse()` crossing a boundary | No schema validation | Deserialize with proto decoder |
| Giant 30-field message | Impossible to review, version, or extend | Split by concern, max 12 fields |
| Storing raw JSON in Lakebase | Loses queryability and type safety | Map to `repeated`, `map`, or nested message fields |
| Shared mutable state between modules | Race conditions, unclear ownership | Communicate through typed messages |

## References

- [Plugin Contract Details](references/plugin-contracts.md) — proto↔plugin type mappings for files, lakebase, jobs
