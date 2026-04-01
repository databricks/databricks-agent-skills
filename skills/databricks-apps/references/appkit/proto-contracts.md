# Plugin Contract Reference

Concrete proto↔plugin mappings for the three core AppKit plugins.

## Files Plugin Contract

**Plugin manifest**: `files/manifest.json`
**Resource**: UC Volume with `WRITE_VOLUME` permission
**Env**: `DATABRICKS_VOLUME_FILES` for volume path

### Boundary: What the files plugin owns

The files plugin is the ONLY module that touches UC Volumes. Other modules
interact with files through typed proto messages, never raw paths.

```
┌─────────────┐    UploadRequest     ┌──────────────┐
│ api module   │ ──────────────────→ │ files plugin  │
│              │ ←────────────────── │              │
│              │    StoredArtifact    │  UC Volumes   │
└─────────────┘                      └──────────────┘
```

### Proto → Plugin Method Mapping

| Proto Message | Plugin Method | Direction |
|---------------|---------------|-----------|
| `UploadRequest` | `files.upload(path, content, opts)` | IN |
| `StoredArtifact` | Return type of upload/getInfo | OUT |
| `VolumeLayout` | `files.config.volumePath` + conventions | CONFIG |

### Volume Path Convention (from VolumeLayout proto)

```
/Volumes/{catalog}/{schema}/{volume}/
├── uploads/                    # User uploads (UploadRequest.destination_path)
├── results/                    # Computed outputs (StoredArtifact)
│   └── {run_id}/
│       ├── output.proto.bin    # Binary proto serialization
│       └── output.json         # JSON for debugging
└── artifacts/                  # Build artifacts, archives
    └── {app_name}/
        └── {version}/
```

### Config ↔ Proto Mapping

| manifest.json field | Proto field | Notes |
|---------------------|-------------|-------|
| `config.timeout` (30000) | Not in proto | Plugin-internal config |
| `config.maxUploadSize` (5GB) | `UploadRequest.content` max size | Validation constraint |
| `resources.path` env | `VolumeLayout.root` | Runtime injection |

---

## Lakebase Plugin Contract

**Plugin manifest**: `lakebase/manifest.json`
**Resource**: Postgres with `CAN_CONNECT_AND_CREATE` permission
**Env**: `PGHOST`, `PGDATABASE`, `PGPORT`, `PGSSLMODE`, `LAKEBASE_ENDPOINT`

### Boundary: What the lakebase plugin owns

Lakebase owns ALL structured data. Every table's schema is derived from a proto
message in `database.proto`. No ad-hoc `CREATE TABLE` statements.

```
┌─────────────┐    RunRecord         ┌──────────────┐
│ compute mod  │ ──────────────────→ │ lakebase      │
│              │                     │ plugin        │
│              │    MetricRecord     │              │
│              │ ──────────────────→ │  Postgres     │
└─────────────┘                      └──────┬───────┘
                                            │
┌─────────────┐    SQL query               │
│ analytics   │ ←──────────────────────────┘
│ module      │    RunRecord[]
└─────────────┘
```

### Proto → Table Mapping

| Proto Message | Table Name | Primary Key | Notes |
|---------------|-----------|-------------|-------|
| `RunRecord` | `runs` | `(run_id, app_name)` | One row per run |
| `MetricRecord` | `metrics` | auto-increment | FK to runs.run_id |
| `ConfigRecord` | `configs` | `config_id` | Versioned configs |

### Proto → DDL Type Mapping

| Proto Type | SQL Type | Column Default |
|-----------|----------|----------------|
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
| `enum` | `TEXT` | First value name |

### Migration Convention

```
migrations/
├── 001_create_runs.sql
├── 002_create_metrics.sql
├── 003_create_configs.sql
└── 004_add_metrics_index.sql
```

Each migration is idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).

### Config ↔ Proto Mapping

| manifest.json field | Proto usage | Notes |
|---------------------|-------------|-------|
| `resources.branch` | Not in proto | Infrastructure config |
| `resources.database` | Not in proto | Infrastructure config |
| `resources.host` (`PGHOST`) | Connection string | Runtime injection |
| `resources.databaseName` (`PGDATABASE`) | Database selection | Runtime injection |

---

## Jobs / Compute Contract

**No plugin manifest** — Jobs are invoked via `@databricks/sdk-experimental`
**Resource**: Databricks Jobs API
**Auth**: Workspace token or OAuth

### Boundary: What the jobs module owns

The jobs module owns compute execution. It receives typed task inputs, runs them
on Databricks clusters, and produces typed task outputs.

```
┌─────────────┐    JobConfig         ┌──────────────┐
│ api module   │ ──────────────────→ │ jobs module   │
│              │                     │              │
│              │    JobTaskInput     │  Databricks   │
│              │ ──────────────────→ │  Jobs API     │
│              │                     │              │
│              │    JobTaskOutput    │  Clusters     │
│              │ ←────────────────── │              │
└─────────────┘                      └──────────────┘
```

### Proto → Jobs SDK Mapping

| Proto Message | SDK Method | Direction |
|---------------|-----------|-----------|
| `JobConfig` | `jobs.create(config)` | IN — defines the job |
| `TaskConfig` | Task within a job | IN — defines task deps |
| `JobTaskInput` | Task params (base64 proto) | IN — task receives |
| `JobTaskOutput` | Task output (written to Volume) | OUT — task produces |

### Task Parameter Convention

Job tasks receive their typed input via:
1. **Small payloads (<256KB)**: Base64-encoded proto in task params
2. **Large payloads**: Proto binary written to UC Volume, path passed as param

```typescript
// Producer (api module)
const input: JobTaskInput = { taskId, taskType, runId, inputPayload };
const encoded = Buffer.from(JobTaskInput.encode(input).finish()).toString('base64');
// Pass as notebook parameter: { "input": encoded }

// Consumer (job task code)
const decoded = JobTaskInput.decode(Buffer.from(params.input, 'base64'));
```

### Task Output Convention

Job tasks write their typed output to:
```
/Volumes/{catalog}/{schema}/{volume}/results/{run_id}/{task_id}.output.bin
```

The output is a serialized `JobTaskOutput` proto. The orchestrator reads it
back with the generated decoder.

### Jobs API Patterns

```typescript
// Create a multi-task job from JobConfig proto
const jobConfig: JobConfig = {
  jobName: `${appName}-${runId}`,
  clusterSpec: '{"num_workers": 1}',
  maxRetries: 2,
  timeoutSeconds: 3600,
  tasks: [
    { taskKey: 'generate', taskType: 'generate', dependsOn: [] },
    { taskKey: 'evaluate', taskType: 'evaluate', dependsOn: ['generate'] },
    { taskKey: 'aggregate', taskType: 'aggregate', dependsOn: ['evaluate'] },
  ],
};
```
