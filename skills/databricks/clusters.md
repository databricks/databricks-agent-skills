# Clusters

Databricks Clusters provide compute resources for interactive analysis and batch jobs.

## Cluster Commands

### List and Get Clusters

```bash
# List clusters
databricks clusters list --profile my-workspace

# Get cluster details
databricks clusters get --cluster-id <cluster-id> --profile my-workspace
```

### Create Cluster

```bash
# Create cluster from JSON config
databricks clusters create --json @cluster-config.json --profile my-workspace
```

**cluster-config.json**:
```json
{
  "cluster_name": "my-cluster",
  "spark_version": "13.3.x-scala2.12",
  "node_type_id": "i3.xlarge",
  "num_workers": 2,
  "autotermination_minutes": 30
}
```

### Edit Cluster

```bash
# Edit cluster configuration
databricks clusters edit --json @updated-config.json --profile my-workspace
```

**Note**: Cluster must be terminated to edit configuration.

### Delete Cluster

```bash
# Terminate cluster (can be restarted)
databricks clusters delete --cluster-id <cluster-id> --profile my-workspace

# Permanently delete cluster
databricks clusters permanent-delete --cluster-id <cluster-id> --profile my-workspace
```

## Cluster Lifecycle

### Start Cluster

```bash
# Start a terminated cluster
databricks clusters start --cluster-id <cluster-id> --profile my-workspace
```

### Restart Cluster

```bash
# Restart a running cluster
databricks clusters restart --cluster-id <cluster-id> --profile my-workspace
```

### Resize Cluster

```bash
# Resize cluster (change number of workers)
databricks clusters resize \
  --cluster-id <cluster-id> \
  --num-workers 5 \
  --profile my-workspace
```

## Cluster Events

```bash
# List cluster events (logs, state changes)
databricks clusters events --cluster-id <cluster-id> --profile my-workspace

# Get recent events with limit
databricks clusters events \
  --cluster-id <cluster-id> \
  --limit 100 \
  --profile my-workspace
```

## Cluster Configuration Examples

### Basic Interactive Cluster

```json
{
  "cluster_name": "interactive-cluster",
  "spark_version": "13.3.x-scala2.12",
  "node_type_id": "i3.xlarge",
  "num_workers": 2,
  "autotermination_minutes": 30,
  "spark_conf": {
    "spark.speculation": "true"
  }
}
```

### Auto-Scaling Cluster

```json
{
  "cluster_name": "autoscaling-cluster",
  "spark_version": "13.3.x-scala2.12",
  "node_type_id": "i3.xlarge",
  "autoscale": {
    "min_workers": 2,
    "max_workers": 10
  },
  "autotermination_minutes": 60
}
```

### Single-Node Cluster

```json
{
  "cluster_name": "single-node-cluster",
  "spark_version": "13.3.x-scala2.12",
  "node_type_id": "i3.xlarge",
  "num_workers": 0,
  "spark_conf": {
    "spark.master": "local[*, 4]",
    "spark.databricks.cluster.profile": "singleNode"
  },
  "custom_tags": {
    "ResourceClass": "SingleNode"
  }
}
```

### High Concurrency Cluster

```json
{
  "cluster_name": "shared-cluster",
  "spark_version": "13.3.x-scala2.12",
  "node_type_id": "i3.xlarge",
  "autoscale": {
    "min_workers": 2,
    "max_workers": 8
  },
  "autotermination_minutes": 120,
  "spark_conf": {
    "spark.databricks.cluster.profile": "serverless"
  }
}
```

### GPU Cluster

```json
{
  "cluster_name": "gpu-cluster",
  "spark_version": "13.3.x-gpu-ml-scala2.12",
  "node_type_id": "g4dn.xlarge",
  "num_workers": 2,
  "autotermination_minutes": 30,
  "init_scripts": [{
    "dbfs": {
      "destination": "dbfs:/databricks/scripts/gpu-init.sh"
    }
  }]
}
```

## Cluster Libraries

### Install Library

```bash
# Install Maven library
databricks libraries install \
  --cluster-id <cluster-id> \
  --maven-coordinates "group:artifact:version" \
  --profile my-workspace

# Install PyPI package
databricks libraries install \
  --cluster-id <cluster-id> \
  --pypi-package "pandas==1.5.3" \
  --profile my-workspace

# Install from DBFS
databricks libraries install \
  --cluster-id <cluster-id> \
  --whl "dbfs:/FileStore/wheels/my_package.whl" \
  --profile my-workspace
```

### List Libraries

```bash
# List cluster libraries
databricks libraries list --cluster-id <cluster-id> --profile my-workspace
```

### Uninstall Library

```bash
# Uninstall library
databricks libraries uninstall \
  --cluster-id <cluster-id> \
  --pypi-package "pandas" \
  --profile my-workspace
```

## Cluster Policies

Cluster policies enforce standards and cost controls.

```bash
# List cluster policies
databricks cluster-policies list --profile my-workspace

# Get policy details
databricks cluster-policies get --policy-id <policy-id> --profile my-workspace
```

## Best Practices

### 1. Use Auto-Termination

Always set auto-termination to avoid unnecessary costs:

```json
{
  "autotermination_minutes": 30  // Terminate after 30 min idle
}
```

### 2. Use Auto-Scaling

Enable auto-scaling for variable workloads:

```json
{
  "autoscale": {
    "min_workers": 2,
    "max_workers": 10
  }
}
```

### 3. Choose Appropriate Node Types

- **General purpose**: `i3.xlarge`, `i3.2xlarge`
- **Memory optimized**: `r5.xlarge`, `r5.2xlarge`
- **Compute optimized**: `c5.xlarge`, `c5.2xlarge`
- **GPU**: `g4dn.xlarge`, `p3.2xlarge`

### 4. Use Cluster Pools

Create cluster pools for faster cluster startup:

```bash
databricks instance-pools create --json @pool-config.json --profile my-workspace
```

### 5. Tag Clusters for Cost Tracking

```json
{
  "custom_tags": {
    "Project": "Analytics",
    "Team": "Data-Science",
    "Environment": "Production"
  }
}
```

### 6. Use Init Scripts Sparingly

Only use init scripts when necessary:
- Installing system packages
- Configuring environment
- Setting up monitoring agents

```json
{
  "init_scripts": [{
    "dbfs": {
      "destination": "dbfs:/databricks/init-scripts/setup.sh"
    }
  }]
}
```

### 7. Prefer Job Clusters Over Interactive

For scheduled workloads:
- ✅ Use job clusters (cheaper, auto-managed)
- ❌ Avoid long-running interactive clusters

## Troubleshooting

### Cluster Won't Start

**Symptom**: Cluster stuck in "Pending" or fails to start

**Solution**:
1. Check workspace capacity
2. Verify node type availability
3. Review cluster configuration
4. Check init script errors
5. Verify instance pools have capacity

### Cluster Terminated Unexpectedly

**Symptom**: Cluster terminated without user action

**Solution**:
1. Check auto-termination setting
2. Review cluster events log
3. Check for workspace-level policies
4. Verify no out-of-memory errors
5. Check cloud provider status

### Library Installation Fails

**Symptom**: Library won't install on cluster

**Solution**:
1. Verify library specification is correct
2. Check cluster has internet access (for PyPI/Maven)
3. Restart cluster after installation
4. Check for dependency conflicts
5. Review cluster logs

### Performance Issues

**Symptom**: Jobs running slow on cluster

**Solution**:
1. Increase number of workers or enable auto-scaling
2. Use larger node types
3. Optimize Spark configuration
4. Check for data skew
5. Review job execution plan

### Out of Memory Errors

**Symptom**: Tasks failing with OOM errors

**Solution**:
1. Use memory-optimized node types
2. Increase number of workers
3. Optimize data processing (reduce shuffles)
4. Increase driver memory
5. Partition data more evenly

## Spark Configuration

Common Spark configurations:

```json
{
  "spark_conf": {
    "spark.speculation": "true",
    "spark.sql.adaptive.enabled": "true",
    "spark.sql.adaptive.coalescePartitions.enabled": "true",
    "spark.databricks.delta.preview.enabled": "true"
  }
}
```

## Environment Variables

Set environment variables for the cluster:

```json
{
  "spark_env_vars": {
    "PYSPARK_PYTHON": "/databricks/python3/bin/python3",
    "MY_CUSTOM_VAR": "value"
  }
}
```

## Related Topics

- [Jobs](jobs.md) - Use clusters in jobs
- [DBFS](dbfs.md) - Store init scripts and libraries
- [Workspace](workspace.md) - Run notebooks on clusters
