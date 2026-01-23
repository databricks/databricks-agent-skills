# AI/BI Dashboards

AI/BI Dashboards (formerly Lakeview) provide interactive analytics with natural language capabilities powered by AI.

## Dashboard Commands

### List Dashboards

```bash
# List all AI/BI dashboards
databricks lakeview list --profile my-workspace
```

### Get Dashboard

```bash
# Get dashboard details
databricks lakeview get --dashboard-id <dashboard-id> --profile my-workspace
```

### Publish Dashboard

```bash
# Publish a dashboard
databricks lakeview publish --dashboard-id <dashboard-id> --profile my-workspace

# Publish specific version
databricks lakeview publish \
  --dashboard-id <dashboard-id> \
  --version-id <version-id> \
  --profile my-workspace
```

### Unpublish Dashboard

```bash
# Unpublish a dashboard
databricks lakeview unpublish --dashboard-id <dashboard-id> --profile my-workspace
```

## Managing Dashboards with Asset Bundles

AI/BI dashboards can be managed in bundle configuration using the `dashboard` resource type.

### Generate Dashboard Configuration

```bash
# Generate dashboard config from existing dashboard
databricks bundle generate dashboard <dashboard-id> --profile my-workspace
```

This creates a bundle resource configuration and downloads the dashboard definition.

### Bundle Dashboard Configuration

```yaml
# resources/dashboards/sales_dashboard.yml
resources:
  dashboards:
    sales_dashboard:
      display_name: "Sales Analytics Dashboard"
      warehouse_id: ${var.warehouse_id}
      file_path: ./dashboards/sales_dashboard.lvdash.json
```

### Deploy Dashboard with Bundle

```bash
# Validate
databricks bundle validate --profile my-workspace

# Deploy
databricks bundle deploy -t prod --profile my-workspace
```

## Dashboard Features

### Natural Language Queries

AI/BI Dashboards support natural language questions:

1. **Ask questions in plain English**
   - "What were the top 10 products by revenue last month?"
   - "Show me sales trends over the past year"
   - "Which regions had the highest growth?"

2. **AI generates SQL automatically**
   - Understands your data schema
   - Creates appropriate queries
   - Returns results with visualizations

### Interactive Visualizations

- **Auto-generated charts** based on query results
- **Drag-and-drop** dashboard builder
- **Responsive layouts** for different screen sizes
- **Real-time updates** when data changes

### Collaboration

- **Share dashboards** with teams
- **Embed** in other applications
- **Schedule refresh** for latest data
- **Version control** via Asset Bundles

## Creating Dashboards

### Using the UI

1. **Open AI/BI Dashboards** in Databricks workspace
2. **Create new dashboard**
3. **Connect to SQL Warehouse**
4. **Add visualizations**:
   - Ask natural language questions
   - Write SQL queries
   - Import from saved queries
5. **Arrange and style** dashboard
6. **Publish** when ready

### Using Asset Bundles

```yaml
# databricks.yml
resources:
  dashboards:
    customer_analytics:
      display_name: "Customer Analytics"
      warehouse_id: "${var.warehouse_id}"
      file_path: ./dashboards/customer_analytics.lvdash.json
```

## Dashboard Lifecycle

### Development Workflow

1. **Create dashboard** in UI
2. **Iterate on design** and queries
3. **Generate bundle config**:
   ```bash
   databricks bundle generate dashboard <dashboard-id> --profile my-workspace
   ```
4. **Commit to version control**
5. **Deploy to other environments**:
   ```bash
   databricks bundle deploy -t staging --profile my-workspace
   databricks bundle deploy -t prod --profile my-workspace
   ```

### Publishing

```bash
# Publish draft to make it accessible
databricks lakeview publish --dashboard-id <dashboard-id> --profile my-workspace
```

**Published dashboards**:
- Accessible to users with view permissions
- Immutable (create new version for changes)
- Can be embedded in other apps
- Suitable for production use

## Dashboard Configuration

### SQL Warehouse Connection

Dashboards require a SQL warehouse:

```yaml
resources:
  dashboards:
    my_dashboard:
      warehouse_id: "${var.warehouse_id}"  # Reference warehouse
```

### Permissions

Control who can view/edit dashboards:
- Set in workspace UI
- Managed through workspace permissions
- Use groups for team access

### Refresh Schedule

Configure automatic data refresh:
- Set refresh intervals in UI
- Ensure SQL warehouse is running
- Consider cost of frequent refreshes

## Best Practices

### 1. Use Descriptive Names

```yaml
resources:
  dashboards:
    sales_performance_q4:  # Good: Specific and descriptive
      display_name: "Q4 Sales Performance Dashboard"
```

### 2. Organize by Purpose

```
dashboards/
├── executive/
│   ├── company_overview.lvdash.json
│   └── financial_summary.lvdash.json
├── sales/
│   ├── regional_performance.lvdash.json
│   └── product_analytics.lvdash.json
└── operations/
    └── logistics_metrics.lvdash.json
```

### 3. Optimize Queries

- Use appropriate filters
- Leverage table partitioning
- Cache frequently accessed data
- Consider materialized views

### 4. Design for Your Audience

- **Executive dashboards**: High-level metrics, trends
- **Operational dashboards**: Real-time data, actionable insights
- **Analytical dashboards**: Detailed data, drill-down capabilities

### 5. Version Control

Always use Asset Bundles:
- Track changes over time
- Deploy consistently across environments
- Collaborate with team
- Rollback if needed

### 6. Use Variables

```yaml
variables:
  warehouse_id:
    description: "SQL Warehouse for dashboards"

targets:
  dev:
    variables:
      warehouse_id: "dev_warehouse_id"

  prod:
    variables:
      warehouse_id: "prod_warehouse_id"
```

### 7. Test Before Publishing

1. Verify all queries work
2. Check visualizations display correctly
3. Test with sample data
4. Review with stakeholders
5. Publish to production

## Troubleshooting

### Dashboard Won't Load

**Symptom**: Dashboard shows error or doesn't load

**Solution**:
1. Check SQL warehouse is running
2. Verify queries are valid
3. Check data source permissions
4. Review query timeouts
5. Check for errors in dashboard logs

### Queries Failing

**Symptom**: Queries return errors

**Solution**:
1. Verify table/view exists
2. Check Unity Catalog permissions
3. Test query in SQL editor
4. Verify warehouse has capacity
5. Check for SQL syntax errors

### Slow Performance

**Symptom**: Dashboard takes long to load

**Solution**:
1. Optimize underlying queries
2. Use larger SQL warehouse
3. Add appropriate filters
4. Consider data aggregation
5. Use materialized views

### Cannot Publish

**Symptom**: Publish fails

**Solution**:
1. Verify you have publish permissions
2. Check all queries are valid
3. Ensure visualizations are configured
4. Review error messages
5. Contact workspace admin

### Bundle Generate Fails

**Symptom**: Cannot generate dashboard config

**Solution**:
1. Verify dashboard ID is correct
2. Check you have read permissions
3. Ensure dashboard exists
4. Try publishing dashboard first
5. Check CLI version is up to date

## Integration with Other Services

### Unity Catalog

Dashboards can query Unity Catalog tables:

```sql
SELECT * FROM my_catalog.analytics.sales_data
WHERE date >= current_date() - INTERVAL 30 DAYS
```

### Databricks SQL

Use existing SQL queries:
- Import saved queries
- Reference DBSQL dashboards
- Share SQL warehouses

### Genie Integration

AI/BI Dashboards work with Genie:
- Natural language understanding
- Automatic visualization selection
- Intelligent query suggestions

## Related Topics

- [DBSQL](dbsql.md) - SQL warehouses and queries
- [Unity Catalog](unity-catalog.md) - Query UC tables
- [Genie](genie.md) - AI-powered data analysis
- [Asset Bundles](asset-bundles.md) - Manage dashboards as code
