# Lakebase Computes and Scaling

## Compute Sizing

Each Compute Unit (CU) allocates ~2 GB of RAM.

| Category | Range | Notes |
|----------|-------|-------|
| **Autoscale** | 0.5–64 CU | Dynamic scaling (max − min <= 16 CU) |
| **Fixed-size** | 0.5–64 CU, or any whole number from 65 to 112 CU (larger sizes are fixed only) | No autoscaling. The Lakebase App lists only some sizes; the CLI, API, SDK and bundles accept any whole CU |

**Allowed CU values:** 0.5 or a whole number. The API rejects other fractions such as 1.5 (`autoscaling limit must be an integer or 0.25 or 0.50`) and anything below 0.5 (`must be at least 0.5 CU`).

| CU | RAM | Max Connections |
|----|-----|-----------------|
| 0.5 | ~1 GB | 105 |
| 1 | ~2 GB | 218 |
| 4 | ~8 GB | 894 |
| 8 | ~16 GB | 1,795 |
| 16 | ~32 GB | 3,597 |
| 24+ | ~48 GB+ | 3,993 (cap) |

## Endpoint Operations

Each branch can have only one read-write endpoint. Run `databricks postgres <subcommand> -h` to discover exact flags.

```bash
# Create endpoint with autoscaling
databricks postgres create-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_WRITE", "autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 4.0}}' \
  --profile <PROFILE>

# Get endpoint details (host, state, CU range)
databricks postgres get-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>

# List endpoints on a branch
databricks postgres list-endpoints projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>

# Resize (update_mask specifies which fields to change)
databricks postgres update-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
  --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}' \
  --profile <PROFILE>

# Delete endpoint
databricks postgres delete-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>
```

## Autoscaling Configuration

- **Range:** 0.5–64 CU. **Constraint:** Max − Min <= 16 CU.
- **Valid:** 4–20 CU, 8–24 CU, 48–64 CU. **Invalid:** 0.5–32 CU (spread of 31.5).
- Set minimum CU large enough to cache your working set in memory.
- Connection limits are based on the smaller of the **max CU** and **8 × min CU** (for example, 2–8 CU gets the 8 CU limit, but 0.5–8 CU gets the 4 CU limit).

## Scale-to-Zero

Automatically suspends compute after inactivity. Default timeout: 24 hours. Range: 60 seconds to 7 days. Only available for computes of 32 CU or smaller (autoscaling max ≤ 32 CU).

To resize a compute above 32 CU, turn off scale-to-zero in the same `update-endpoint` call: add `spec.no_suspension` to the update mask and set `"no_suspension": true`. Otherwise the update fails with `scale to 0 is not allowed for computes larger than the configured threshold`.

| Branch | Default |
|--------|---------|
| `production` | Scale-to-zero **enabled**, 24 h timeout (turn it off for always-on workloads) |
| Other branches | Configurable |

**Wake-up:** Compute restarts automatically within a few hundred milliseconds when a connection arrives. Restarts at minimum CU. Applications should implement retry logic for the brief reactivation period.

**Session context is reset on reactivation:**
- Temporary tables and prepared statements are lost
- Session settings and in-memory cache are cleared
- Connection pools and active transactions are terminated
- Advisory locks released, NOTIFY/LISTEN subscriptions lost

## High Availability

1 primary + 1–3 secondary compute instances across availability zones. GA on AWS and Azure.

**How it works:**
- Secondaries are hot standbys promoted automatically if primary fails
- All instances share the same storage layer
- Total: 2–4 compute instances per HA endpoint

**Connection strings:** an HA endpoint has a primary host, which follows the current primary after failover, and a read-only host (`-ro` suffix) for readable secondaries, available only when *Allow access to read-only compute instances* is on. Copy both from the project's **Connect** dialog or `get-endpoint`; don't build them by hand.

**Enabling HA:** Configured at the endpoint level. Run `databricks postgres create-endpoint -h` and `databricks postgres update-endpoint -h` for spec fields. Each secondary can be Read-only (serves reads) or Disabled (failover standby only).

**Failover behavior:**
- All committed transactions are preserved
- Active connections are terminated — applications must reconnect
- Primary connection string routes to promoted secondary transparently
- With only one readable secondary, read traffic is interrupted during failover

**HA secondaries vs read replicas:**

| Feature | HA Secondaries | Read Replicas |
|---------|---------------|---------------|
| Purpose | Failover + optional reads | Read offload only |
| Failover | Yes, auto-promoted | No |
| Connection | Shared `-ro` string | Separate endpoint |
| Sizing | Floor at primary CU, can scale above | Independent |
| Scale-to-zero | Not supported | Configurable |

**Constraints:**
- Scale-to-zero not supported with HA
- Max autoscaling spread remains 16 CU
- Secondaries autoscale independently but will not scale below the primary's current CU size
- Minimum 2, maximum 4 compute instances

## Sizing Guidance

- Use `EXPLAIN ANALYZE` to understand query plans — **rows examined** is the most actionable metric
- Create covering indexes for frequent queries (include filter + sort columns)
- Paginate queries that can return unbounded result sets
- Keep transactions short and deterministic to avoid lock contention
- Follow consistent table access order within transactions to prevent deadlocks
