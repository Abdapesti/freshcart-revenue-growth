-- Grain: one row per submitted order. Rank completed orders separately so
-- cancelled orders never become a customer's "first completed order".
WITH completed_rank AS (
  SELECT order_id,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_at, order_id) AS completed_order_number
  FROM orders
  WHERE order_status = 'completed'
)
SELECT f.order_id, f.customer_id, f.order_at, f.order_month,
       f.hub_city AS city, f.acquisition_channel, f.order_status,
       f.item_subtotal, f.discount_amount, f.refund_amount,
       f.product_cost, f.delivery_fee, f.service_fee,
       CASE WHEN r.completed_order_number = 1 THEN 1 ELSE 0 END AS is_first_completed_order
FROM fact_orders AS f
LEFT JOIN completed_rank AS r ON r.order_id = f.order_id
ORDER BY f.order_at, f.order_id;
