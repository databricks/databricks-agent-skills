# DBSQL (Databricks SQL)

Databricks SQL provides a SQL-native experience for data warehousing and analytics with SQL warehouses, queries, dashboards, and alerts.

## SQL Warehouses

SQL Warehouses provide compute resources for running SQL queries.

### List and Get Warehouses

```bash
# List SQL warehouses
databricks warehouses list --profile my-workspace

# Get warehouse details
databricks warehouses get --id <warehouse-id> --profile my-workspace
```

### Create SQL Warehouse

```bash
# Create a SQL warehouse
databricks warehouses create \
  --name "my-warehouse" \
  --cluster-size "2X-Small" \
  --min-num-clusters 1 \
  --max-num-clusters 1 \
  --profile my-workspace

# Create with auto-stop
databricks warehouses create \
  --name "auto-stop-warehouse" \
  --cluster-size "Small" \
  --min-num-clusters 1 \
  --max-num-clusters 3 \
  --auto-stop-mins 10 \
  --profile my-workspace
```

### Warehouse Sizes

- **2X-Small**: 1 DBU per hour
- **X-Small**: 2 DBUs per hour
- **Small**: 4 DBUs per hour
- **Medium**: 8 DBUs per hour
- **Large**: 16 DBUs per hour
- **X-Large**: 32 DBUs per hour
- **2X-Large**: 64 DBUs per hour
- **3X-Large**: 128 DBUs per hour
- **4X-Large**: 256 DBUs per hour

### Start and Stop Warehouses

```bash
# Start a warehouse
databricks warehouses start --id <warehouse-id> --profile my-workspace

# Stop a warehouse
databricks warehouses stop --id <warehouse-id> --profile my-workspace
```

### Update Warehouse

```bash
# Update warehouse configuration
databricks warehouses edit \
  --id <warehouse-id> \
  --name "updated-name" \
  --cluster-size "Medium" \
  --max-num-clusters 5 \
  --profile my-workspace
```

### Delete Warehouse

```bash
# Delete a warehouse
databricks warehouses delete --id <warehouse-id> --profile my-workspace
```

## Queries

SQL queries can be managed programmatically.

### List and Get Queries

```bash
# List queries
databricks queries list --profile my-workspace

# Get query details
databricks queries get --id <query-id> --profile my-workspace
```

### Create Query

```bash
# Create query from JSON config
databricks queries create --json @query-config.json --profile my-workspace
```

**query-config.json**:
```json
{
  "name": "Daily Sales Report",
  "query": "SELECT * FROM sales WHERE date = current_date()",
  "data_source_id": "<warehouse-id>",
  "description": "Daily sales summary"
}
```

### Update Query

```bash
# Update query
databricks queries update --id <query-id> --json @updated-query.json --profile my-workspace
```

### Delete Query

```bash
# Delete query
databricks queries delete --id <query-id> --profile my-workspace
```

## Dashboards

Dashboards provide visualizations of your data.

### List and Get Dashboards

```bash
# List dashboards
databricks dashboards list --profile my-workspace

# Get dashboard details
databricks dashboards get --id <dashboard-id> --profile my-workspace
```

### Generate Dashboard Configuration

Use Asset Bundles to manage dashboards:

```bash
# Generate dashboard config for bundle
databricks bundle generate dashboard <dashboard-id> --profile my-workspace
```

This creates a bundle resource configuration for the dashboard.

## Alerts

Alerts notify you when query results meet certain conditions.

### List and Get Alerts

```bash
# List alerts
databricks alerts list --profile my-workspace

# Get alert details
databricks alerts get --id <alert-id> --profile my-workspace
```

### Create Alert

```bash
# Create alert from JSON config
databricks alerts create --json @alert-config.json --profile my-workspace
```

**alert-config.json**:
```json
{
  "name": "High Error Rate Alert",
  "query_id": "<query-id>",
  "options": {
    "column": "error_count",
    "op": ">",
    "value": 100
  },
  "rearm": 300
}
```

### Update Alert

```bash
# Update alert
databricks alerts update --id <alert-id> --json @updated-alert.json --profile my-workspace
```

### Delete Alert

```bash
# Delete alert
databricks alerts delete --id <alert-id> --profile my-workspace
```

## DBSQL Workflow

### 1. Create SQL Warehouse

```bash
databricks warehouses create \
  --name "analytics-warehouse" \
  --cluster-size "Small" \
  --min-num-clusters 1 \
  --max-num-clusters 3 \
  --auto-stop-mins 10 \
  --profile my-workspace
```

### 2. Get Warehouse ID

```bash
# List warehouses to get ID
databricks warehouses list --profile my-workspace
```

### 3. Create Query

```json
{
  "name": "Daily Revenue",
  "query": "SELECT date, SUM(amount) as revenue FROM sales GROUP BY date ORDER BY date DESC",
  "data_source_id": "<warehouse-id>"
}
```

```bash
databricks queries create --json @query.json --profile my-workspace
```

### 4. Create Dashboard

Create dashboards in the UI or use Asset Bundles to manage them.

### 5. Set Up Alerts

```json
{
  "name": "Low Revenue Alert",
  "query_id": "<query-id>",
  "options": {
    "column": "revenue",
    "op": "<",
    "value": 10000
  },
  "rearm": 3600
}
```

```bash
databricks alerts create --json @alert.json --profile my-workspace
```

## Best Practices

### 1. Right-Size Your Warehouse

Start small and scale based on:
- Query complexity
- Data volume
- Concurrent users
- Performance requirements

```bash
# Start with Small
--cluster-size "Small"

# Scale up if needed
--cluster-size "Medium"
```

### 2. Enable Auto-Stop

Save costs by auto-stopping idle warehouses:

```bash
--auto-stop-mins 10  # Stop after 10 minutes of inactivity
```

### 3. Use Auto-Scaling

Allow warehouses to scale based on demand:

```bash
--min-num-clusters 1 \
--max-num-clusters 5  # Scale up to 5 clusters
```

### 4. Organize Queries

Use descriptive names and add descriptions:

```json
{
  "name": "Daily Sales by Region",
  "description": "Shows daily sales breakdown by region, updated hourly",
  "query": "..."
}
```

### 5. Use Query Parameters

Make queries reusable with parameters:

```sql
-- Query with parameter
SELECT * FROM sales
WHERE date = {{ date_param }}
AND region = {{ region_param }}
```

### 6. Monitor Warehouse Usage

Regularly review:
- Query execution times
- Warehouse utilization
- Cost per query
- Auto-stop effectiveness

### 7. Separate Workloads

Use different warehouses for different purposes:

```bash
# Development warehouse (small, aggressive auto-stop)
databricks warehouses create \
  --name "dev-warehouse" \
  --cluster-size "X-Small" \
  --auto-stop-mins 5

# Production warehouse (larger, longer running)
databricks warehouses create \
  --name "prod-warehouse" \
  --cluster-size "Large" \
  --auto-stop-mins 30
```

## Troubleshooting

### Warehouse Won't Start

**Symptom**: Warehouse fails to start or gets stuck in "STARTING" state

**Solution**:
1. Check workspace capacity
2. Verify warehouse configuration
3. Check for permission issues
4. Try stopping and restarting
5. Contact workspace admin if issue persists

### Query Fails

**Symptom**: Query returns error or doesn't complete

**Solution**:
1. Check SQL syntax
2. Verify table/view exists and you have access
3. Check warehouse is running
4. Review error message for specific issue
5. Verify Unity Catalog permissions

### Slow Query Performance

**Symptom**: Queries taking too long to execute

**Solution**:
1. Increase warehouse size
2. Enable auto-scaling
3. Optimize query (add filters, use partitions)
4. Check data volume
5. Review query execution plan

### Alert Not Triggering

**Symptom**: Alert condition met but no notification

**Solution**:
1. Verify alert is enabled
2. Check alert condition configuration
3. Verify notification destinations are configured
4. Check query is returning expected results
5. Review alert rearm period

### Dashboard Not Loading

**Symptom**: Dashboard shows error or doesn't display

**Solution**:
1. Check underlying queries are working
2. Verify warehouse is running
3. Check permissions on queries and data
4. Refresh dashboard
5. Check for query timeouts

## Integration with Unity Catalog

DBSQL works seamlessly with Unity Catalog:

```sql
-- Query Unity Catalog tables
SELECT * FROM prod_catalog.sales_schema.daily_sales;

-- Create views in Unity Catalog
CREATE VIEW prod_catalog.analytics.sales_summary AS
SELECT date, SUM(amount) as total_sales
FROM prod_catalog.sales_schema.daily_sales
GROUP BY date;
```

## Related Topics

- [Unity Catalog](unity-catalog.md) - Query UC tables
- [AI/BI Dashboards](ai-bi-dashboards.md) - Enhanced dashboards with AI
- [Asset Bundles](asset-bundles.md) - Manage DBSQL resources as code
- [Workflows](workflows.md) - Complete analytics workflows
