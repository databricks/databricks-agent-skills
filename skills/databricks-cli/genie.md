# Databricks Genie

Databricks Genie provides AI-powered data analysis and natural language querying capabilities.

## What is Genie?

Genie is an AI assistant that:
- Understands natural language questions about your data
- Automatically generates SQL queries
- Provides insights and visualizations
- Learns from your data schema and relationships

## Genie Commands

### List Genie Spaces

```bash
# List all Genie spaces
databricks genie list-spaces --profile my-workspace
```

### Get Genie Space

```bash
# Get Genie space details
databricks genie get-space --space-id <space-id> --profile my-workspace
```

### Create Genie Space

```bash
# Create a Genie space from JSON config
databricks genie create-space --json @genie-config.json --profile my-workspace
```

**genie-config.json**:
```json
{
  "display_name": "Sales Analytics Genie",
  "description": "Genie space for sales data analysis",
  "warehouse_id": "<warehouse-id>"
}
```

## Genie Spaces

Genie Spaces are workspaces where you can:
- Have conversations with Genie about your data
- Ask questions in natural language
- Get AI-generated queries and insights
- Share conversations with team members

### Space Configuration

```json
{
  "display_name": "Customer Analytics",
  "description": "Analyze customer behavior and trends",
  "warehouse_id": "<warehouse-id>",
  "data_sources": [
    "my_catalog.sales.customers",
    "my_catalog.sales.orders",
    "my_catalog.sales.products"
  ]
}
```

## Using Genie

### Primary Usage: Web UI

Genie is primarily used through the Databricks workspace UI:

1. **Open Genie** from workspace navigation
2. **Select or create a space**
3. **Ask questions** in natural language
4. **Review AI-generated queries**
5. **Refine and iterate** on results
6. **Save useful queries** for reuse

### Natural Language Questions

Examples of questions you can ask Genie:

**Sales Analysis**:
- "What were the top 10 products by revenue last quarter?"
- "Show me sales trends by region for the past year"
- "Which customers have the highest lifetime value?"

**Customer Analytics**:
- "How many new customers did we acquire last month?"
- "What's the average order value by customer segment?"
- "Show me customer retention rates over time"

**Operational Metrics**:
- "What's the average time to fulfill an order?"
- "Which warehouses have the highest inventory turnover?"
- "Show me delivery performance by carrier"

### Genie Features

**AI-Generated SQL**:
- Genie converts your questions to SQL
- Reviews and understands your data schema
- Handles joins and aggregations automatically
- Optimizes queries for performance

**Iterative Refinement**:
- Ask follow-up questions
- Refine previous queries
- Drill down into results
- Change visualization types

**Knowledge Building**:
- Genie learns from your data schema
- Understands relationships between tables
- Recognizes business terminology
- Improves over time with usage

## Managing Genie Spaces

### Permissions

Control access to Genie spaces:
- **Owner**: Full control over the space
- **Editor**: Can ask questions and modify space
- **Viewer**: Can view conversations (read-only)

Set permissions in the workspace UI.

### Data Sources

Connect Genie to your data:

```json
{
  "data_sources": [
    "production_catalog.sales.orders",
    "production_catalog.sales.customers",
    "production_catalog.analytics.daily_metrics"
  ]
}
```

Genie can query:
- Unity Catalog tables
- Views
- Materialized views
- External tables

### SQL Warehouse

Each Genie space requires a SQL warehouse:

```json
{
  "warehouse_id": "<warehouse-id>"
}
```

Ensure the warehouse:
- Is running or set to auto-start
- Has sufficient capacity
- Has access to required catalogs/schemas

## Best Practices

### 1. Organize by Use Case

Create separate spaces for different purposes:

```bash
# Create space for sales analytics
databricks genie create-space --json @sales-genie.json --profile my-workspace

# Create space for marketing analytics
databricks genie create-space --json @marketing-genie.json --profile my-workspace

# Create space for operations
databricks genie create-space --json @ops-genie.json --profile my-workspace
```

### 2. Use Descriptive Names

```json
{
  "display_name": "Q4 Sales Performance Analysis",
  "description": "Analyze Q4 sales data across regions and product lines"
}
```

### 3. Connect Relevant Data Sources

Only include tables that are relevant to the space's purpose:

```json
{
  "data_sources": [
    "sales_catalog.analytics.orders",
    "sales_catalog.analytics.customers",
    "sales_catalog.analytics.products"
    // Don't include unrelated tables
  ]
}
```

### 4. Document Business Logic

Add descriptions to your tables and columns in Unity Catalog:

```sql
-- This helps Genie understand your data
COMMENT ON TABLE sales.orders IS 'Customer orders including online and in-store purchases';
COMMENT ON COLUMN sales.orders.revenue IS 'Total revenue in USD after discounts';
```

### 5. Save Useful Queries

When Genie generates a useful query:
- Save it as a SQL query in DBSQL
- Add it to a dashboard
- Share with team members
- Reuse in future analysis

### 6. Provide Feedback

Help Genie improve:
- Use thumbs up/down on responses
- Clarify when results aren't what you expected
- Refine questions if needed
- Report issues or unexpected behavior

### 7. Review Generated SQL

Always review the SQL Genie generates:
- Verify it's querying the right tables
- Check filters and aggregations
- Ensure results make sense
- Optimize if needed

## Use Cases

### Executive Analytics

```
Questions:
- "What's our revenue growth compared to last quarter?"
- "Show me top performing products this month"
- "What are the key trends in customer acquisition?"

Data Sources:
- sales.revenue_summary
- products.performance_metrics
- customers.acquisition_metrics
```

### Operational Analysis

```
Questions:
- "Which warehouses have low inventory levels?"
- "What's the average delivery time by region?"
- "Show me fulfillment rates for the past week"

Data Sources:
- inventory.warehouse_levels
- logistics.delivery_metrics
- orders.fulfillment_data
```

### Customer Intelligence

```
Questions:
- "Who are our most valuable customers?"
- "What products do high-value customers buy?"
- "Show me customer churn trends"

Data Sources:
- customers.profiles
- customers.purchase_history
- customers.engagement_metrics
```

## Integration with Other Services

### Unity Catalog

Genie queries Unity Catalog tables:
- Understands catalog/schema/table structure
- Respects permissions and access controls
- Uses column descriptions and comments

### AI/BI Dashboards

Convert Genie insights to dashboards:
1. Ask question in Genie
2. Review generated query
3. Save query to DBSQL
4. Add to AI/BI Dashboard
5. Share with team

### DBSQL

Genie uses SQL warehouses from DBSQL:
- Shared compute resources
- Same permissions model
- Compatible query syntax

## Limitations

1. **SQL Generation**: Genie generates SQL, so it's limited to what SQL can do
2. **Data Understanding**: Works best with well-structured, documented data
3. **Complex Logic**: Very complex business logic may need manual SQL
4. **Real-time Data**: Limited by underlying data freshness

## Troubleshooting

### Genie Not Understanding Questions

**Symptom**: Genie returns irrelevant results or errors

**Solution**:
1. Rephrase question more specifically
2. Use table/column names in question
3. Add descriptions to UC tables/columns
4. Break complex questions into simpler parts
5. Review and edit generated SQL

### Cannot Access Data

**Symptom**: "Permission denied" or "Table not found"

**Solution**:
1. Verify SQL warehouse has access to catalogs
2. Check Unity Catalog permissions
3. Ensure tables are in connected data sources
4. Verify tables exist in the catalog

### Slow Responses

**Symptom**: Genie takes long to respond

**Solution**:
1. Check SQL warehouse is running
2. Increase warehouse size if needed
3. Optimize underlying data tables
4. Add appropriate indexes
5. Consider materialized views for complex queries

### Incorrect Results

**Symptom**: Query results don't match expectations

**Solution**:
1. Review generated SQL
2. Check data quality in source tables
3. Verify filters and aggregations
4. Clarify question with more details
5. Manually adjust SQL if needed

## Related Topics

- [AI/BI Dashboards](ai-bi-dashboards.md) - Create dashboards from Genie insights
- [DBSQL](dbsql.md) - SQL warehouses and queries
- [Unity Catalog](unity-catalog.md) - Data sources for Genie
