# Lakebase High Availability

## Overview

Lakebase Autoscaling supports high availability (HA) by pairing a primary compute with secondary compute instances distributed across availability zones. HA provides automatic failover for OLTP workloads. GA on both AWS and Azure.

## How HA Works

- A branch has one **primary** read-write compute and 1–3 **secondary** compute instances in different AZs
- Secondaries are hot standbys that can be promoted if the primary fails
- All compute instances share the same underlying storage layer
- Total: 2–4 compute instances per HA configuration (1 primary + 1–3 secondaries)

## Connection Strings

| String | Format | Routes To |
|--------|--------|-----------|
| **Primary** | `{endpoint-id}.database.{region}.databricks.com` | Current primary (read-write) |
| **Read-only** | `{endpoint-id}-ro.database.{region}.databricks.com` | Readable secondaries |

- The primary connection string automatically routes to whichever compute is currently primary, including after failover — no application reconfiguration needed.
- The read-only string is available only when "Allow access to read-only compute instances" is enabled on at least one secondary.
- Individual compute instance connection strings exist for troubleshooting only — do not use for application traffic.

## Enabling HA

Use the CLI to discover the exact spec fields for HA configuration:

```bash
databricks postgres create-endpoint -h
databricks postgres update-endpoint -h
```

HA is configured at the endpoint level. Each secondary can be set to **Read-only** (serves read traffic) or **Disabled** (failover standby only).

## Failover Behavior

1. Lakebase continuously monitors primary health
2. If the primary becomes unavailable, a secondary is automatically promoted
3. **All committed transactions are preserved** during failover
4. Active connections are terminated — applications must reconnect
5. The primary connection string routes to the newly promoted compute

**Read traffic during failover:**
- If the promoted secondary was serving reads, it stops — reads continue at reduced capacity if other readable secondaries exist
- With only one readable secondary, read traffic is interrupted until a replacement is provisioned

## HA Secondaries vs Read Replicas

| Feature | HA Secondaries | Read Replicas |
|---------|---------------|---------------|
| **Purpose** | Failover + optional read offload | Read offload only |
| **Failover** | Yes — automatically promoted | No |
| **Connection** | Shared `-ro` string on primary endpoint | Separate independent endpoint |
| **Sizing** | Shared with primary (endpoint-level) | Independently sized |
| **Scale-to-zero** | Not supported (HA constraint) | Configurable |

Both features can coexist on the same branch for combined HA and additional read capacity.

## Constraints

- **Scale-to-zero:** Not supported when HA is enabled. Manually pausing all instances makes the endpoint unavailable.
- **Autoscaling range:** Max spread remains 16 CU with HA.
- **Secondary sizing:** Secondaries always scale to at least the same CU size as the primary to preserve capacity after failover.
- **Minimum configuration:** 2 compute instances (1 primary + 1 secondary).
- **Maximum configuration:** 4 compute instances (1 primary + 3 secondaries).

## Best Practices

1. **Implement connection retry logic** — configure TCP keepalives and connection timeouts so applications reconnect quickly after failover
2. **Use at least two readable secondaries** if offloading reads — ensures read traffic continues during failover when one secondary is promoted
3. **Monitor secondary utilization** — if secondaries become overloaded with read traffic, increase CU size or add read replicas
4. **Size secondaries appropriately** — secondaries share the primary's autoscaling range, so set the range based on combined read + failover needs
