---
name: trigger-and-cost-optimization
description: Select and tune triggers for Spark Structured Streaming to balance latency and cost. Use when choosing between processingTime, availableNow, and Real-Time Mode (RTM), calculating optimal trigger intervals, optimizing costs through cluster right-sizing, scheduled streaming, multi-stream clusters, or managing latency vs cost trade-offs.
---

# Trigger and Cost Optimization

Select and tune triggers to balance latency requirements with cost. Optimize streaming job costs through trigger tuning, cluster right-sizing, multi-stream clusters, storage optimization, and scheduled execution patterns.

## Quick Start

```python
# Cost-optimized: Scheduled streaming instead of continuous
df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/stream") \
    .trigger(availableNow=True) \
    .start("/delta/target")  # Process all, then stop

# Schedule via Databricks Jobs: Every 15 minutes
# Cost: ~$20/day for 100 tables on 8-core cluster
```

## Trigger Types

### ProcessingTime Trigger

Process at fixed intervals:

```python
# Trigger clause used in a writeStream chain:
writer = df.writeStream.format("delta").option("checkpointLocation", "/checkpoints/stream")

# Process every 30 seconds
writer.trigger(processingTime="30 seconds").start("/delta/target")

# Process every 5 minutes
writer.trigger(processingTime="5 minutes").start("/delta/target")

# Latency: Trigger interval + processing time
# Cost: Continuous cluster running
```

### AvailableNow Trigger

Process all available data, then stop:

```python
# Process all available data, then stop
df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/stream") \
    .trigger(availableNow=True) \
    .start("/delta/target")

# Schedule via Databricks Jobs:
# - Every 15 minutes: Near real-time
# - Every 4 hours: Batch-style

# Latency: Schedule interval + processing time
# Cost: Cluster runs only during processing
```

### Real-Time Mode (RTM)

Sub-second end-to-end latency (as low as 5 ms). Cluster requirements, slot math, supported sources/sinks, observability, error classes — see [real-time-mode.md](real-time-mode.md).

```python
# "5 minutes" is the long-running batch duration; PySpark requires it explicitly.
.trigger(realTime="5 minutes")

# Cost: Continuous cluster (Photon disabled — required for RTM)
```

## Trigger Selection Guide

| Latency Requirement | Trigger | Cost | Use Case |
|---------------------|---------|------|----------|
| Sub-second (as low as 5ms) | RTM | $$$ | Real-time analytics, alerts, operational apps |
| 1-30 seconds | processingTime | $$ | Near real-time dashboards |
| 15-60 minutes | availableNow (scheduled) | $ | Batch-style SLA |
| > 1 hour | availableNow (scheduled) | $ | ETL pipelines |

**Default choice for demos and prototypes:** prefer `availableNow` unless the user has explicitly asked for continuous or sub-second processing. RTM keeps a Classic cluster running 24/7 (see [Real-Time Mode](real-time-mode.md) for why), which is easy to spin up and forget about. `availableNow` runs on demand and terminates — the safe default when latency isn't a first-order concern.

## Trigger Interval Calculation

### Rule of Thumb: SLA / 3

```python
# Calculate trigger interval from SLA
business_sla_minutes = 60  # 1 hour SLA
trigger_interval_minutes = business_sla_minutes / 3  # 20 minutes

writer.trigger(processingTime=f"{trigger_interval_minutes} minutes").start()

# Why /3?
# - Processing time buffer
# - Recovery time buffer
# - Safety margin
```

### Example Calculations

```python
# Example 1: 1 hour SLA
sla = 60  # minutes
trigger = sla / 3  # 20 minutes
writer.trigger(processingTime="20 minutes").start()

# Example 2: 15 minute SLA
sla = 15  # minutes
trigger = sla / 3  # 5 minutes
writer.trigger(processingTime="5 minutes").start()

# Example 3: Real-time requirement
.trigger(realTime="5 minutes")  # sub-second E2E latency; "5 minutes" = long-running batch duration
```

## Cost Optimization Strategies

### Strategy 1: Trigger Interval Tuning

Balance latency and cost:

```python
# Shorter interval = higher cost
writer.trigger(processingTime="5 seconds").start()   # Expensive - continuous processing

# Longer interval = lower cost
writer.trigger(processingTime="5 minutes").start()   # Cheaper - less frequent processing

# Use availableNow for batch-style (cheapest)
writer.trigger(availableNow=True).start()            # Process backlog, then stop

# Rule of thumb: SLA / 3
# Example: 1 hour SLA → 20 minute trigger
```

### Strategy 2: Scheduled vs Continuous

Choose execution pattern based on SLA:

| Pattern | Cost | Latency | Use Case |
|---------|------|---------|----------|
| Continuous | $$$ | < 1 minute | Real-time requirements |
| 15-min schedule | $$ | 15-30 minutes | Near real-time |
| 4-hour schedule | $ | 4-5 hours | Batch-style SLA |

```python
# Continuous (expensive)
writer.trigger(processingTime="30 seconds").start()

# Scheduled (cost-effective)
writer.trigger(availableNow=True).start()  # Schedule via Jobs: Every 15 minutes

# Batch-style (cheapest)
writer.trigger(availableNow=True).start()  # Schedule via Jobs: Every 4 hours
```

### Strategy 3: Cluster Right-Sizing

Right-size clusters based on workload:

```python
# Don't oversize:
# - Monitor CPU utilization (target 60-80%)
# - Check for idle time
# - Use fixed-size clusters (no autoscaling for streaming)

# Scale test approach:
# 1. Start small
# 2. Monitor lag (max offsets behind latest)
# 3. Scale up if falling behind
# 4. Right-size based on steady state
```

### Strategy 4: Multi-Stream Clusters

Run multiple streams on one cluster:

```python
# Run multiple streams on one cluster
# Tested: 100 streams on 8-core single-node cluster
# Cost: ~$20/day for 100 tables

# Example: Multiple streams on same cluster
stream1.writeStream.option("checkpointLocation", "/checkpoints/stream1").start()
stream2.writeStream.option("checkpointLocation", "/checkpoints/stream2").start()
stream3.writeStream.option("checkpointLocation", "/checkpoints/stream3").start()
# ... up to 100+ streams

# Monitor: CPU/memory per stream
# Scale cluster if aggregate utilization > 80%
```

### Strategy 5: Storage Optimization

Reduce storage costs:

```sql
-- VACUUM old files
VACUUM table RETAIN 24 HOURS;

-- Enable auto-optimize to reduce small files
ALTER TABLE table SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = true,
    'delta.autoOptimize.autoCompact' = true
);

-- Archive old data to cheaper storage
-- Use data retention policies
```

## Cost Formula

```
Daily Cost = 
    (Cluster DBU/hour × Hours running) +
    (Storage GB × Storage rate) +
    (Network egress if applicable)

Optimization levers:
- Reduce hours running (scheduled triggers)
- Reduce cluster size (right-sizing)
- Reduce storage (VACUUM, compression)
- Reduce network egress (co-locate compute and storage)
```

## Common Patterns

### Pattern 1: Cost-Optimized Scheduled Streaming

Convert continuous to scheduled:

```python
# Before: Continuous (expensive)
df.writeStream \
    .trigger(processingTime="30 seconds") \
    .start()

# After: Scheduled (cost-effective)
df.writeStream \
    .trigger(availableNow=True) \
    .start()  # Process all, then stop

# Schedule via Databricks Jobs:
# - Every 15 minutes: Near real-time
# - Every 4 hours: Batch-style
# Same code, different schedule
```

### Pattern 2: Multi-Stream Cluster

Optimize cluster utilization:

```python
# Run multiple streams on one cluster
def start_all_streams():
    streams = []
    
    # Start multiple streams
    for i in range(100):
        stream = (spark
            .readStream
            .table(f"source_{i}")
            .writeStream
            .format("delta")
            .option("checkpointLocation", f"/checkpoints/stream_{i}")
            .trigger(availableNow=True)
            .start(f"/delta/target_{i}")
        )
        streams.append(stream)
    
    return streams

# Monitor aggregate CPU/memory
# Scale cluster if needed
```

### Pattern 3: RTM for Sub-Second Latency

Use RTM for real-time requirements. See [real-time-mode.md](real-time-mode.md) for the deep treatment.

```python
# Real-Time Mode — sub-second E2E latency (as low as 5 ms)
df.writeStream \
    .format("kafka") \
    .option("topic", "output") \
    .outputMode("update") \
    .trigger(realTime="5 minutes") \
    .start()

# Cost: Continuous cluster (Photon disabled)
```

## Real-Time Mode (RTM) Configuration

Cluster setup, Spark conf, supported operations, sources/sinks, slot math, observability — all in [real-time-mode.md](real-time-mode.md). This file covers only the cost-vs-trigger trade-off; RTM's cost shape is "continuous cluster with Photon disabled."

## Performance Considerations

### Batch Duration vs Trigger Interval

```python
# Batch duration should be < trigger interval
# Example:
trigger_interval = 30  # seconds
batch_duration = 10  # seconds

# Healthy: batch_duration < trigger_interval
# Unhealthy: batch_duration >= trigger_interval

# Monitor in Spark UI:
# - Batch duration
# - Trigger interval
# - Alert if batch duration >= trigger interval
```

### Trigger Interval Tuning

```python
# Start conservative, optimize based on monitoring
# Step 1: Start with SLA / 3
trigger_interval = business_sla / 3

# Step 2: Monitor batch duration
# If batch duration < trigger_interval / 2: Can increase trigger
# If batch duration >= trigger_interval: Decrease trigger

# Step 3: Optimize for cost vs latency
# Increase trigger interval to reduce cost
# Decrease trigger interval to reduce latency
```

## Cost Monitoring

### Track Per-Stream Costs

```python
# Tag jobs with stream name
job_tags = {
    "stream_name": "orders_stream",
    "environment": "prod",
    "cost_center": "analytics"
}

# Use DBU consumption metrics
# Monitor by workspace/cluster
# Track cost per stream over time
```

### Monitor Cluster Utilization

```python
# Check CPU utilization
# Target: 60-80% utilization
# Below 60%: Consider downsizing
# Above 80%: Consider upsizing

# Check memory utilization
# Monitor for OOM errors
# Adjust cluster size accordingly
```

## Latency vs Cost Trade-offs

### Continuous Processing

```python
# High cost, low latency
writer.trigger(processingTime="30 seconds").start()

# Cost: Continuous cluster running
# Latency: 30 seconds + processing time
# Use when: Real-time requirements
```

### Scheduled Processing

```python
# Lower cost, higher latency
writer.trigger(availableNow=True).start()  # Schedule: Every 15 minutes

# Cost: Cluster runs only during processing
# Latency: Schedule interval + processing time
# Use when: Batch-style SLA acceptable
```

### Real-Time Mode

```python
# Highest cost, lowest latency
.trigger(realTime="5 minutes")  # "5 minutes" = long-running batch duration

# Cost: Continuous cluster (Photon disabled)
# Latency: Sub-second E2E (as low as 5 ms)
# Use when: Sub-second latency required
```

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **High latency** | Trigger interval too long | Decrease trigger interval or use RTM |
| **High cost** | Continuous processing | Use scheduled (availableNow) |
| **Batch duration > trigger** | Processing too slow | Optimize processing or increase trigger |
| **RTM not working** | Cluster misconfigured | Verify: DBR 16.4 LTS+ (18.1+ recommended), Classic compute, autoscaling/Photon/spot OFF, `spark.databricks.streaming.realTimeMode.enabled = true`. See [real-time-mode.md](real-time-mode.md). |

## Quick Wins

1. **Change from continuous to 15-minute schedule** - Significant cost reduction
2. **Run multiple streams per cluster** - Better cluster utilization
3. **Enable auto-optimize** - Reduce storage costs
4. **Use Spot instances** - For non-critical streams (with caution)
5. **Archive old data** - Move to cheaper storage tiers

## Trade-offs

| Cost Reduction | Impact | Mitigation |
|----------------|--------|------------|
| Longer trigger | Higher latency | Acceptable if SLA allows |
| Smaller cluster | May fall behind | Monitor lag; scale if needed |
| Aggressive VACUUM | Less time travel | Balance retention vs cost |
| Spot instances | Possible interruptions | Use for non-critical streams |
| Scheduled vs continuous | Higher latency | Match to business SLA |

## Production Best Practices

### Match Trigger to SLA

```python
# Calculate trigger from business SLA
def calculate_trigger_interval(sla_minutes):
    """Calculate optimal trigger interval"""
    return max(30, sla_minutes / 3)  # Minimum 30 seconds

trigger_interval = calculate_trigger_interval(business_sla_minutes)
writer.trigger(processingTime=f"{trigger_interval} seconds").start()
```

### Cluster Configuration

```python
# Fixed-size cluster (no autoscaling for streaming)
cluster_config = {
    "num_workers": 4,
    "node_type_id": "i3.xlarge",
    "autotermination_minutes": 60,  # Terminate if idle
    "enable_elastic_disk": True  # Reduce storage costs
}
```

### Storage Management

```sql
-- Enable auto-optimize
ALTER TABLE table SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = true,
    'delta.autoOptimize.autoCompact' = true
);

-- Periodic VACUUM
VACUUM table RETAIN 7 DAYS;  -- Balance retention vs cost

-- Archive old partitions
-- Move to cheaper storage tier
```

## Production Checklist

- [ ] Trigger type selected based on latency requirements
- [ ] Trigger interval calculated from SLA (SLA / 3)
- [ ] Batch duration monitored (< trigger interval)
- [ ] Cluster right-sized (60-80% utilization)
- [ ] Multiple streams per cluster (if applicable)
- [ ] Scheduled execution (if SLA allows)
- [ ] RTM configured if sub-second latency required
- [ ] Auto-optimize enabled
- [ ] Storage costs monitored
- [ ] Cost per stream tracked

## Related Skills

- `kafka-streaming` - RTM configuration for Kafka pipelines
- `checkpoint-best-practices` - Checkpoint management
