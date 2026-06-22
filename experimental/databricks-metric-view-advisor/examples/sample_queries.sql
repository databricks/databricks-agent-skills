-- Sample queries for Input Source 3 (Queries + Schema)
-- These represent typical analytical queries that the metric view advisor
-- can analyze to suggest metric view definitions.

-- Query 1: Monthly revenue by region
SELECT region,
       DATE_TRUNC('MONTH', order_date) AS month,
       SUM(amount) AS revenue,
       COUNT(1) AS order_count
FROM catalog.schema.orders
GROUP BY 1, 2
ORDER BY 1, 2;

-- Query 2: Top customers by spend
SELECT customer_id,
       SUM(amount) AS total_spend,
       COUNT(1) AS order_count,
       AVG(amount) AS avg_order_value
FROM catalog.schema.orders
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;

-- Query 3: Order fulfillment rate by month
SELECT DATE_TRUNC('MONTH', order_date) AS month,
       COUNT(1) AS total_orders,
       COUNT(1) FILTER (WHERE status = 'FULFILLED') AS fulfilled_orders,
       COUNT(1) FILTER (WHERE status = 'FULFILLED') * 1.0 / COUNT(1) AS fulfillment_rate
FROM catalog.schema.orders
GROUP BY 1
ORDER BY 1;

-- Query 4: Revenue by product category (star schema join)
SELECT p.category,
       DATE_TRUNC('QUARTER', o.order_date) AS quarter,
       SUM(o.amount) AS revenue,
       COUNT(DISTINCT o.customer_id) AS unique_customers
FROM catalog.schema.orders o
JOIN catalog.schema.products p ON o.product_id = p.product_id
GROUP BY 1, 2
ORDER BY 1, 2;

-- Query 5: Customer segment analysis
SELECT CASE WHEN c.lifetime_value > 10000 THEN 'Enterprise'
            WHEN c.lifetime_value > 1000 THEN 'Mid-Market'
            ELSE 'SMB' END AS segment,
       SUM(o.amount) AS revenue,
       COUNT(DISTINCT o.customer_id) AS customers,
       SUM(o.amount) / COUNT(DISTINCT o.customer_id) AS revenue_per_customer
FROM catalog.schema.orders o
JOIN catalog.schema.customers c ON o.customer_id = c.customer_id
GROUP BY 1
ORDER BY 2 DESC;
