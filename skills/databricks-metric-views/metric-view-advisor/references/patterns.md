# Metric View Patterns — Advisor Templates

Key patterns to use as templates when generating metric view suggestions. These
are the advisor's curated, **metadata-rich** templates — every dimension and
measure carries `comment`/`display_name`/`synonyms` where useful, because the
suggestion step (Step 3) leans on that metadata for Genie discoverability.

> **Requires the parent skill.** Additional patterns live **only** in the
> **`databricks-metric-views`** skill (the advisor depends on it; it is not
> optional). For patterns this file does not duplicate, see that skill →
> `references/patterns.md`: a dedicated **Ratio Measures** pattern, a **Filtered
> Measures (FILTER clause)** pattern, a **TPC-H `samples` demo** pattern, a
> **Materialized Metric View** pattern, the fuller **Window Measures** breakdown
> (each variant isolated, plus query examples), and **ALTER / query-with-filters**
> examples. The patterns kept here are the ones whose advisor version is materially
> richer or safer (full semantic metadata, quoted `'on':` join keys, correct
> snowflake dot-chaining, and a window-measures example that composes
> backtick-quoted multi-word measure names).

## Contents

- [Pattern 1: Simple Single-Table Metrics](#pattern-1-simple-single-table-metrics)
- [Pattern 2: Composability + Humanized Dimensions](#pattern-2-composability--humanized-dimensions-recommended)
- [Pattern 3: Star Schema with Joins](#pattern-3-star-schema-with-joins)
- [Pattern 4: Snowflake Schema (Nested Joins)](#pattern-4-snowflake-schema-nested-joins)
- [Pattern 5: Window Measures](#pattern-5-window-measures-trailing-cumulative-period-over-period)
- [Pattern 6: SQL Query as Source](#pattern-6-sql-query-as-source-fallback-for-incompatible-joins)
- [Deploying and Querying via the CLI](#deploying-and-querying-via-the-cli)

## Pattern 1: Simple Single-Table Metrics

```sql
CREATE OR REPLACE VIEW catalog.schema.product_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Product sales metrics"
  source: catalog.schema.sales
  dimensions:
    - name: Product Name
      expr: product_name
      comment: "Name of the product"
      display_name: "Product Name"
      synonyms:
        - 'product'
        - 'item name'
    - name: Sale Date
      expr: sale_date
      comment: "Date of the sale"
      display_name: "Sale Date"
      synonyms:
        - 'date'
        - 'transaction date'
  measures:
    - name: Units Sold
      expr: COUNT(1)
      comment: "Total number of units sold"
      display_name: "Units Sold"
      synonyms:
        - 'quantity'
        - 'unit count'
    - name: Total Revenue
      expr: SUM(price * quantity)
      comment: "Total revenue from sales"
      display_name: "Total Revenue"
      synonyms:
        - 'total sales'
        - 'gross revenue'
    - name: Average Price
      expr: AVG(price)
      comment: "Average unit price"
      display_name: "Average Price"
      synonyms:
        - 'avg price'
        - 'mean price'
$$
```

### Query Examples

```sql
-- Revenue by product
SELECT `Product Name`, MEASURE(`Total Revenue`) AS revenue, MEASURE(`Units Sold`) AS units
FROM catalog.schema.product_metrics
GROUP BY ALL ORDER BY revenue DESC LIMIT 10

-- Monthly trend
SELECT DATE_TRUNC('MONTH', `Sale Date`) AS month, MEASURE(`Total Revenue`) AS revenue
FROM catalog.schema.product_metrics
GROUP BY ALL ORDER BY month
```

## Pattern 2: Composability + Humanized Dimensions (Recommended)

Atomic measures first, composed measures via `MEASURE()`, and CASE-based dimension value standardization per Databricks best practices.

```sql
CREATE OR REPLACE VIEW catalog.schema.order_status_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Order metrics with status breakdowns, composable ratios, and business-friendly dimensions"
  source: catalog.schema.orders
  filter: "order_date > '2020-01-01'"

  dimensions:
    - name: Order Date
      expr: order_date
      comment: "Granular order date for detail-level analysis"
      display_name: "Order Date"
    - name: Order Month
      expr: "DATE_TRUNC('MONTH', order_date)"
      comment: "Month of order for trend analysis"
      display_name: "Order Month"
    - name: Region
      expr: region
      comment: "Sales region"
    - name: Order Status
      expr: "CASE WHEN status = 'O' THEN 'Open' WHEN status = 'F' THEN 'Fulfilled' WHEN status = 'P' THEN 'Processing' END"
      comment: "Human-readable order status"
      display_name: "Order Status"
      synonyms:
        - 'status'
        - 'fulfillment status'
    - name: Priority Level
      expr: CASE
        WHEN priority <= 2 THEN 'High'
        WHEN priority <= 4 THEN 'Medium'
        ELSE 'Low'
        END
      comment: "Bucketed priority: High (1-2), Medium (3-4), Low (5+)"

  measures:
    # Step 1: Atomic measures
    - name: Total Orders
      expr: COUNT(1)
    - name: Total Revenue
      expr: SUM(amount)
    - name: Unique Customers
      expr: COUNT(DISTINCT customer_id)
    - name: Fulfilled Orders
      expr: COUNT(1) FILTER (WHERE status = 'F')
      comment: "Orders that have been fulfilled"
    - name: Open Orders
      expr: COUNT(1) FILTER (WHERE status = 'O')
      comment: "Orders not yet fulfilled"
    - name: Open Revenue
      expr: SUM(amount) FILTER (WHERE status = 'O')
      comment: "Revenue at risk from unfulfilled orders"

    # Step 2: Composed measures (backtick-quote multi-word names in MEASURE)
    - name: Fulfillment Rate
      expr: "MEASURE(`Fulfilled Orders`) / MEASURE(`Total Orders`)"
      comment: "Percentage of orders fulfilled"
    - name: Revenue per Customer
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Unique Customers`)"
      comment: "Average revenue per unique customer"
    - name: Avg Order Value
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Total Orders`)"
      comment: "Average order value"
$$
```

## Pattern 3: Star Schema with Joins

Join a fact table to dimension tables for richer slicing. Note the quoted `'on':`
keys (see the gotchas table in [yaml-reference.md](yaml-reference.md)) and the
`source.`-prefixed fact columns.

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_analytics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Sales analytics with customer and product dimensions"
  source: catalog.schema.fact_sales

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      'on': source.customer_id = customer.customer_id
    - name: product
      source: catalog.schema.dim_product
      'on': source.product_id = product.product_id
    - name: store
      source: catalog.schema.dim_store
      'on': source.store_id = store.store_id

  dimensions:
    - name: Customer Segment
      expr: customer.segment
      comment: "Customer tier: Enterprise, Mid-Market, SMB"
    - name: Product Category
      expr: product.category
      comment: "Product category"
    - name: Store City
      expr: store.city
      comment: "Store location city"
    - name: Sale Month
      expr: DATE_TRUNC('MONTH', source.sale_date)
      comment: "Month of sale"

  measures:
    - name: Total Revenue
      expr: SUM(source.amount)
      comment: "Sum of sale amounts"
    - name: Unique Customers
      expr: COUNT(DISTINCT source.customer_id)
      comment: "Number of distinct customers"
    - name: Average Basket Size
      expr: SUM(source.amount) / COUNT(DISTINCT source.transaction_id)
      comment: "Average revenue per transaction"
$$
```

## Pattern 4: Snowflake Schema (Nested Joins)

Multi-level dimension hierarchies. Requires DBR 17.1+.

**CRITICAL**: Reference nested join columns using the **full dot-chain path** through parent joins. For example, `nation` is nested under `customer`, so use `customer.nation.n_name` — NOT `nation.n_name`. Using just the join name causes `UNRESOLVED_COLUMN` errors.

```sql
CREATE OR REPLACE VIEW catalog.schema.geo_sales
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Sales with geographic hierarchy"
  source: catalog.schema.orders

  joins:
    - name: customer
      source: catalog.schema.customer
      'on': source.customer_key = customer.customer_key
      joins:
        - name: nation
          source: catalog.schema.nation
          'on': customer.nation_key = nation.nation_key
          joins:
            - name: region
              source: catalog.schema.region
              'on': nation.region_key = region.region_key

  dimensions:
    - name: Customer Name
      expr: customer.name
    - name: Nation
      expr: customer.nation.name
      comment: "Full dot-chain: customer -> nation -> name"
    - name: Region
      expr: customer.nation.region.name
      comment: "Full dot-chain: customer -> nation -> region -> name"
    - name: Order Year
      expr: EXTRACT(YEAR FROM source.order_date)

  measures:
    - name: Total Revenue
      expr: SUM(source.total_price)
    - name: Order Count
      expr: COUNT(1)
$$
```

## Pattern 5: Window Measures (Trailing, Cumulative, Period-over-Period)

Time-series patterns using window measures. **Experimental feature.** This is a
representative example; the parent `databricks-metric-views` skill has the fuller
window-measures section (each variant isolated, plus query examples).

```sql
CREATE OR REPLACE VIEW catalog.schema.time_series_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  comment: "Time-series metrics with running totals, trailing windows, and period comparisons. Window measures require version 0.1."
  source: catalog.schema.orders

  dimensions:
    - name: Order Date
      expr: o_orderdate
      comment: "Granular order date"
    - name: Order Year
      expr: EXTRACT(YEAR FROM o_orderdate)

  measures:
    # Atomic
    - name: Daily Revenue
      expr: SUM(o_totalprice)
    - name: Daily Customers
      expr: COUNT(DISTINCT o_custkey)

    # Cumulative running total
    - name: Running Total Revenue
      expr: SUM(o_totalprice)
      window:
        - order: Order Date
          range: cumulative
          semiadditive: last

    # Trailing 7-day window (excludes current day)
    - name: 7-Day Customers
      expr: COUNT(DISTINCT o_custkey)
      window:
        - order: Order Date
          range: trailing 7 day
          semiadditive: last

    # Period-over-period: previous day
    - name: Previous Day Revenue
      expr: SUM(o_totalprice)
      window:
        - order: Order Date
          range: trailing 1 day
          semiadditive: last

    # Composed: day-over-day growth
    - name: Day over Day Growth
      expr: "(MEASURE(`Daily Revenue`) - MEASURE(`Previous Day Revenue`)) / MEASURE(`Previous Day Revenue`) * 100"
      comment: "Percentage change from previous day"

    # Year-to-date (two windows)
    - name: YTD Revenue
      expr: SUM(o_totalprice)
      window:
        - order: Order Date
          range: cumulative
          semiadditive: last
        - order: Order Year
          range: current
          semiadditive: last

    # Semiadditive: balance-like measure (latest value across time)
    - name: Latest Account Balance
      expr: SUM(o_totalprice)
      window:
        - order: Order Date
          range: current
          semiadditive: last
      comment: "Sums across customers but uses latest date value"
$$
```

## Pattern 6: SQL Query as Source (Fallback for Incompatible Joins)

When snowflake joins fail (DBR < 17.1) or cross-join references don't resolve, pre-join tables in the source SQL query. **Note:** Joins block is not supported with SQL query sources.

```sql
CREATE OR REPLACE VIEW catalog.schema.pre_joined_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Pre-joined source for environments where snowflake joins are unsupported"
  source: "(SELECT o.o_orderkey, o.o_totalprice, o.o_orderdate, o.o_orderstatus, o.o_custkey, c.c_mktsegment, n.n_name AS customer_nation, r.r_name AS customer_region FROM catalog.schema.orders o JOIN catalog.schema.customer c ON o.o_custkey = c.c_custkey JOIN catalog.schema.nation n ON c.c_nationkey = n.n_nationkey JOIN catalog.schema.region r ON n.n_regionkey = r.r_regionkey)"

  dimensions:
    - name: Order Date
      expr: o_orderdate
      comment: "Granular order date"
    - name: Order Month
      expr: "DATE_TRUNC('MONTH', o_orderdate)"
      comment: "Month of order"
    - name: Order Status
      expr: "CASE WHEN o_orderstatus = 'O' THEN 'Open' WHEN o_orderstatus = 'F' THEN 'Fulfilled' WHEN o_orderstatus = 'P' THEN 'Processing' END"
      comment: "Human-readable order status"
    - name: Market Segment
      expr: c_mktsegment
    - name: Customer Region
      expr: customer_region
    - name: Customer Nation
      expr: customer_nation

  measures:
    - name: Total Revenue
      expr: SUM(o_totalprice)
    - name: Order Count
      expr: COUNT(1)
    - name: Unique Customers
      expr: COUNT(DISTINCT o_custkey)
    - name: Avg Order Value
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Order Count`)"
    - name: Revenue per Customer
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Unique Customers`)"
$$
```

**When to use:** Prefer native joins; use SQL source only when snowflake joins fail on your DBR version or you need complex join logic. Trade-off: SQL source always scans all joined tables.

## Deploying and Querying via the CLI

Metric views are created, queried, and managed through SQL — see [cli-operations.md](cli-operations.md) for the exact CLI/API commands. There is no dedicated metric-view CLI verb.

### Deploy (create or replace)

Write the full `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$` statement (one of the patterns above) to a `.sql` file and submit it with the **`aitools tools statement`** command — `submit` takes a file path, so the `$$` token-quoting, embedded YAML, and single quotes (e.g. `DATE_TRUNC('MONTH', source.sale_date)`) need no shell/JSON escaping:

```bash
# 1. Write the full CREATE OR REPLACE VIEW ... statement (any pattern above) to a file, e.g. /tmp/sales_metrics.sql

# 2. Submit it — returns a statement_id immediately
databricks experimental aitools tools statement submit --file /tmp/sales_metrics.sql \
  --warehouse <warehouse_id> --profile <PROFILE>

# 3. Block on the statement_id to confirm success
databricks experimental aitools tools statement get <statement_id> --profile <PROFILE>
```

> See [cli-operations.md](cli-operations.md) → *Long DDL* for the full submit/get/status/cancel lifecycle.

### Query (every measure wrapped in MEASURE(), every dimension in GROUP BY)

```bash
databricks experimental aitools tools query "
SELECT \`Customer Segment\`, \`Sale Month\`,
       MEASURE(\`Total Revenue\`) AS \`Total Revenue\`,
       MEASURE(\`Order Count\`) AS \`Order Count\`
FROM catalog.schema.sales_metrics
WHERE \`Customer Segment\` = 'Enterprise'
GROUP BY ALL ORDER BY ALL LIMIT 50
" --profile <PROFILE>
```

### Grant (least privilege)

```sql
GRANT SELECT ON VIEW catalog.schema.sales_metrics TO `data-consumers`;
```
