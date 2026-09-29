CREATE INDEX idx_orders_customer_time ON orders(customer_id, order_at);
CREATE INDEX idx_orders_hub_time ON orders(hub_id, order_at);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_tickets_order ON support_tickets(order_id);

-- One row per order. Aggregate one-to-many tables before joining them.
CREATE VIEW fact_orders AS
WITH item_rollup AS (
  SELECT order_id, SUM(quantity * unit_cost) AS product_cost,
         SUM(is_substituted) AS substituted_lines,
         SUM(quantity) AS units
  FROM order_items GROUP BY order_id
), ticket_rollup AS (
  SELECT order_id, COUNT(*) AS ticket_count
  FROM support_tickets GROUP BY order_id
)
SELECT o.order_id, o.customer_id, o.hub_id, h.city AS hub_city,
       c.city AS customer_city, c.acquisition_channel,
       substr(o.order_at, 1, 7) AS order_month, o.order_at,
       o.order_status, o.item_subtotal, o.discount_amount,
       o.delivery_fee, o.service_fee, o.gross_amount,
       COALESCE(p.paid_amount, 0) AS paid_amount,
       COALESCE(p.refund_amount, 0) AS refund_amount,
       COALESCE(i.product_cost, 0) AS product_cost,
       COALESCE(i.substituted_lines, 0) AS substituted_lines,
       COALESCE(i.units, 0) AS units,
       d.delivery_minutes, d.distance_km, d.is_late,
       COALESCE(t.ticket_count, 0) AS ticket_count
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN hubs h ON h.hub_id = o.hub_id
LEFT JOIN payments p ON p.order_id = o.order_id
LEFT JOIN item_rollup i ON i.order_id = o.order_id
LEFT JOIN deliveries d ON d.order_id = o.order_id
LEFT JOIN ticket_rollup t ON t.order_id = o.order_id;

CREATE VIEW monthly_business_kpis AS
SELECT order_month AS month,
       COUNT(*) AS submitted_orders,
       SUM(order_status = 'completed') AS completed_orders,
       COUNT(DISTINCT CASE WHEN order_status = 'completed' THEN customer_id END) AS monthly_active_customers,
       ROUND(SUM(CASE WHEN order_status = 'completed' THEN item_subtotal ELSE 0 END), 2) AS gmv_idr,
       ROUND(AVG(CASE WHEN order_status = 'completed' THEN item_subtotal END), 2) AS aov_idr,
       ROUND(SUM(CASE WHEN order_status = 'completed' THEN item_subtotal - discount_amount - refund_amount ELSE 0 END), 2) AS net_sales_idr,
       ROUND(SUM(CASE WHEN order_status = 'completed' THEN item_subtotal - discount_amount - refund_amount - product_cost + delivery_fee + service_fee ELSE 0 END), 2) AS contribution_proxy_idr,
       ROUND(1.0 * SUM(order_status = 'cancelled') / COUNT(*), 4) AS cancellation_rate,
       ROUND(1.0 * SUM(CASE WHEN order_status = 'completed' THEN is_late = 0 ELSE 0 END) / NULLIF(SUM(order_status = 'completed'), 0), 4) AS on_time_rate,
       ROUND(1.0 * SUM(CASE WHEN order_status = 'completed' THEN ticket_count > 0 ELSE 0 END) / NULLIF(SUM(order_status = 'completed'), 0), 4) AS contact_rate,
       ROUND(SUM(refund_amount) / NULLIF(SUM(paid_amount), 0), 4) AS refund_rate
FROM fact_orders GROUP BY order_month;

CREATE VIEW monthly_delivery_kpis AS
SELECT order_month AS month, hub_city AS city,
       COUNT(*) AS delivered_orders,
       ROUND(AVG(is_late = 0), 4) AS on_time_rate,
       ROUND(AVG(delivery_minutes), 2) AS avg_delivery_minutes,
       ROUND(AVG(distance_km), 2) AS avg_distance_km
FROM fact_orders WHERE order_status = 'completed'
GROUP BY order_month, hub_city;

CREATE VIEW city_monthly_kpis AS
SELECT order_month AS month, hub_city AS city,
       COUNT(*) AS submitted_orders,
       SUM(order_status = 'completed') AS completed_orders,
       SUM(order_status = 'cancelled') AS cancelled_orders,
       COUNT(DISTINCT CASE WHEN order_status = 'completed' THEN customer_id END) AS active_customers,
       ROUND(SUM(CASE WHEN order_status = 'completed' THEN item_subtotal ELSE 0 END), 2) AS gmv_idr,
       ROUND(SUM(CASE WHEN order_status = 'completed' THEN item_subtotal - discount_amount - refund_amount ELSE 0 END), 2) AS net_sales_idr,
       ROUND(SUM(CASE WHEN order_status = 'completed' THEN item_subtotal - discount_amount - refund_amount - product_cost + delivery_fee + service_fee ELSE 0 END), 2) AS contribution_proxy_idr,
       SUM(CASE WHEN order_status = 'completed' THEN is_late = 0 ELSE 0 END) AS on_time_orders,
       SUM(CASE WHEN order_status = 'completed' THEN ticket_count > 0 ELSE 0 END) AS contact_orders,
       ROUND(SUM(refund_amount), 2) AS refund_idr,
       ROUND(SUM(paid_amount), 2) AS paid_amount_idr,
       ROUND(AVG(CASE WHEN order_status = 'completed' THEN delivery_minutes END), 2) AS avg_delivery_minutes
FROM fact_orders GROUP BY order_month, hub_city;

CREATE VIEW hub_monthly_kpis AS
SELECT f.order_month AS month, f.hub_city AS city, f.hub_id, h.hub_name,
       COUNT(*) AS submitted_orders,
       SUM(f.order_status = 'completed') AS completed_orders,
       SUM(CASE WHEN f.order_status = 'completed' THEN f.is_late = 0 ELSE 0 END) AS on_time_orders,
       SUM(CASE WHEN f.order_status = 'completed' THEN f.ticket_count > 0 ELSE 0 END) AS contact_orders,
       ROUND(SUM(CASE WHEN f.order_status = 'completed' THEN f.item_subtotal ELSE 0 END), 2) AS gmv_idr
FROM fact_orders f JOIN hubs h ON h.hub_id = f.hub_id
GROUP BY f.order_month, f.hub_id;

-- Only full calendar cohorts with an observable 30-day follow-up are included.
CREATE VIEW customer_first_second AS
WITH ranked AS (
  SELECT o.customer_id, o.order_at, h.city AS first_hub_city,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_at, order_id) AS completed_order_number
  FROM orders o JOIN hubs h ON h.hub_id = o.hub_id
  WHERE o.order_status = 'completed'
)
SELECT customer_id,
         MIN(CASE WHEN completed_order_number = 1 THEN order_at END) AS first_order_at,
         MIN(CASE WHEN completed_order_number = 2 THEN order_at END) AS second_order_at,
         MAX(CASE WHEN completed_order_number = 1 THEN first_hub_city END) AS first_hub_city
FROM ranked GROUP BY customer_id;

CREATE VIEW cohort_30d AS
SELECT substr(first_order_at, 1, 7) AS cohort_month,
       COUNT(*) AS acquired_customers,
       SUM(second_order_at IS NOT NULL AND second_order_at <= datetime(first_order_at, '+30 days')) AS repeat_customers_30d,
       ROUND(1.0 * SUM(second_order_at IS NOT NULL AND second_order_at <= datetime(first_order_at, '+30 days')) / COUNT(*), 4) AS repeat_30d_rate
FROM customer_first_second
WHERE date(first_order_at, 'start of month', '+1 month', '+30 days') <= date('2025-12-31')
GROUP BY substr(first_order_at, 1, 7);

CREATE VIEW cohort_city_30d AS
SELECT substr(first_order_at, 1, 7) AS cohort_month,
       first_hub_city AS city,
       COUNT(*) AS acquired_customers,
       SUM(second_order_at IS NOT NULL AND second_order_at <= datetime(first_order_at, '+30 days')) AS repeat_customers_30d
FROM customer_first_second
WHERE date(first_order_at, 'start of month', '+1 month', '+30 days') <= date('2025-12-31')
GROUP BY substr(first_order_at, 1, 7), first_hub_city;
