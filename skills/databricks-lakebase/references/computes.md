# Lakebase Autoscaling Computes

## Overview

A compute is a virtualized service that runs Postgres for a branch. Each branch has one primary read-write compute and can have optional read replicas. Computes support autoscaling, scale-to-zero, and granular sizing from 0.5 to 112 CU.

## Compute Sizing

Each Compute Unit (CU) allocates approximately 2 GB of RAM.

### Available Sizes

| Category | Range | Notes |
|----------|-------|-------|
| **Autoscale computes** | 0.5–32 CU | Dynamic scaling within range (max − min <= 16 CU) |
| **Large fixed-size** | 36–112 CU | Fixed size, no autoscaling |

### Representative Sizes

| Compute Units | RAM | Max Connections |
|--------------|-----|-----------------|
| 0.5 CU | ~1 GB | 104 |
| 1 CU | ~2 GB | 209 |
| 4 CU | ~8 GB | 839 |
| 8 CU | ~16 GB | 1,678 |
| 16 CU | ~32 GB | 3,357 |
| 32 CU | ~64 GB | 4,000 |
| 64 CU | ~128 GB | 4,000 |
| 112 CU | ~224 GB | 4,000 |

**Note:** Lakebase Provisioned used ~16 GB per CU. Autoscaling uses ~2 GB per CU for more granular scaling.

## Creating a Compute

Each branch can have only one read-write compute.

### CLI

```bash
databricks postgres create-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{
    "spec": {
      "endpoint_type": "ENDPOINT_TYPE_READ_WRITE",
      "autoscaling_limit_min_cu": 0.5,
      "autoscaling_limit_max_cu": 4.0
    }
  }' --profile <PROFILE>
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType

w = WorkspaceClient()

result = w.postgres.create_endpoint(
    parent="projects/my-app/branches/production",
    endpoint=Endpoint(
        spec=EndpointSpec(
            endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
            autoscaling_limit_min_cu=0.5,
            autoscaling_limit_max_cu=4.0
        )
    ),
    endpoint_id="my-compute"
).wait()

print(f"Endpoint created: {result.name}")
print(f"Host: {result.status.hosts.host}")
```

## Getting Compute Details

### CLI

```bash
databricks postgres get-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>
```

### Python SDK

```python
endpoint = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
)

print(f"Endpoint: {endpoint.name}")
print(f"Type: {endpoint.status.endpoint_type}")
print(f"State: {endpoint.status.current_state}")
print(f"Host: {endpoint.status.hosts.host}")
print(f"Min CU: {endpoint.status.autoscaling_limit_min_cu}")
print(f"Max CU: {endpoint.status.autoscaling_limit_max_cu}")
```

## Listing Computes

### CLI

```bash
databricks postgres list-endpoints \
  projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

### Python SDK

```python
endpoints = list(w.postgres.list_endpoints(
    parent="projects/my-app/branches/production"
))

for ep in endpoints:
    print(f"Endpoint: {ep.name}")
    print(f"  Type: {ep.status.endpoint_type}")
    print(f"  CU Range: {ep.status.autoscaling_limit_min_cu}-{ep.status.autoscaling_limit_max_cu}")
```

## Resizing a Compute

Use `update_mask` to specify which fields to update.

### CLI

```bash
# Update single field
databricks postgres update-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  spec.autoscaling_limit_max_cu \
  --json '{"spec": {"autoscaling_limit_max_cu": 8.0}}' --profile <PROFILE>

# Update multiple fields
databricks postgres update-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
  --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}' \
  --profile <PROFILE>
```

### Python SDK

```python
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, FieldMask

w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/my-compute",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0
        )
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu"
    ])
).wait()
```

## Deleting a Compute

### CLI

```bash
databricks postgres delete-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>
```

### Python SDK

```python
w.postgres.delete_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
).wait()
```

## Autoscaling Configuration

Autoscaling dynamically adjusts compute resources based on workload demand.

- **Range:** 0.5–32 CU
- **Constraint:** Max − Min cannot exceed 16 CU
- **Valid examples:** 4–20 CU, 8–16 CU, 16–32 CU
- **Invalid example:** 0.5–32 CU (range of 31.5 CU)

### Best Practices

- Set minimum CU large enough to cache your working set in memory
- Performance may be degraded until compute scales up and caches data
- Connection limits are based on the maximum CU in the range

## Scale-to-Zero

Automatically suspends compute after a period of inactivity.

| Setting | Description |
|---------|-------------|
| **Enabled** | Compute suspends after inactivity timeout (saves cost) |
| **Disabled** | Always-active compute (eliminates wake-up latency) |

**Default behavior:**
- `production` branch: Scale-to-zero **disabled** (always active)
- Other branches: Scale-to-zero can be configured

**Default inactivity timeout:** 5 minutes
**Minimum inactivity timeout:** 60 seconds

### Wake-up Behavior

When a connection arrives on a suspended compute:
1. Compute starts automatically (reactivation takes a few hundred milliseconds)
2. The connection request is handled transparently once active
3. Compute restarts at minimum autoscaling size (if autoscaling enabled)
4. Applications should implement connection retry logic for the brief reactivation period

### Session Context After Reactivation

When a compute suspends and reactivates, session context is **reset**:
- In-memory statistics and cache contents are cleared
- Temporary tables and prepared statements are lost
- Session-specific configuration settings reset
- Connection pools and active transactions are terminated

If your application requires persistent session data, consider disabling scale-to-zero.

## Sizing Guidance

| Factor | Recommendation |
|--------|---------------|
| Query complexity | Complex analytical queries benefit from larger computes |
| Concurrent connections | More connections need more CPU and memory |
| Data volume | Larger datasets may need more memory for performance |
| Response time | Critical apps may require larger computes |

### Query Optimization

- Use `EXPLAIN ANALYZE` to understand query plans and identify rows examined
- **Rows examined** is the most actionable metric for performance — minimize it with appropriate indexes
- Create covering indexes for frequently executed queries (include all filter and sort columns)
- Always paginate queries that can return large or unbounded result sets
- Keep transactions short and deterministic to avoid lock contention
- Follow a consistent table access order within transactions to prevent deadlocks
