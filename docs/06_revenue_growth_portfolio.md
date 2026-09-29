# FreshCart 360: Revenue & Growth Methodology

## Business question and scope

This project examines monthly sales, completed order volume, first versus subsequent purchases, and city contributions to GMV for a fictional Indonesian grocery delivery business. All data is synthetic. The analysis describes patterns in the generated dataset; it does not estimate causal effects.

## Reproducible pipeline

1. `src/generate_data.py` produces nine related CSV tables from a fixed seed. `tests/validate_data.py` checks primary and foreign keys, field domains, timestamps, and monetary reconciliation.
2. `src/build_analytics.py` loads the CSVs into SQLite. The `fact_orders` view aggregates line items and tickets before joining, keeping one row per order. `tests/validate_analytics.py` reconciles KPI views against raw CSVs.
3. `sql/revenue_growth_extract.sql` extracts orders and flags each customer's first **completed** order. Cancelled orders do not establish a first purchase. Ties are resolved by `order_at` and `order_id`.
4. `src/build_revenue_growth.py` checks identifiers, required dimensions, dates, order status, monetary values, discount bounds, and the first-order flag. Invalid rows are written to `rejected_rows.csv`. Any rejection stops the pipeline before marts are published; revenue is never silently imputed.
5. Python builds monthly, city, and acquisition-channel marts. `outputs/revenue_growth/index.html` presents charts with year and city filters.
6. `tests/validate_revenue_growth.py` reconciles order counts, GMV, and net sales with independent SQL KPI views and checks segment totals. It also injects invalid duplicate-ID and negative-value examples to test the cleaning rules.

Run the complete sequence in the repository [README](../README.md). The dashboard is an optional local exploration tool; the six-slide PDF is the public summary.

## Metric definitions

- **GMV:** Sum of `item_subtotal` for completed orders, before discounts and fees.
- **Net sales:** GMV minus discounts and refunds attributed to completed orders. It is not profit.
- **Completed orders:** Count of orders with completed status.
- **First-purchase orders:** Count of first completed orders per customer, with timestamp and order ID used for ordering.
- **Subsequent orders:** Completed orders minus first-purchase orders. This is an order count, not a count of unique returning customers.
- **City GMV share:** City GMV divided by total GMV across cities for the selected period.
- **Contribution proxy:** Net sales minus product cost, plus delivery and service fees. It excludes rider, payment-processing, overhead, and campaign costs.

## Results and interpretation

The SQL extract contains 44,472 orders across 24 months in 2024–2025. With seed `42`, all generated rows pass the Python audit. In 2025, the dataset has 27,644 completed orders and about Rp12.95 billion in GMV. These are simulated results, not company performance.

The generator stops adding new customers near the end of 2025. A late-year decline therefore cannot be attributed to service quality or promotions based on these charts. Comparing promotion recipients with an appropriate control group would require a separate experiment or causal design.

## Generated outputs

- `outputs/revenue_growth/sql_extract.csv`: SQL extract before the Python audit.
- `outputs/revenue_growth/clean_orders.csv`: accepted rows and derived monetary metrics.
- `outputs/revenue_growth/cleaning_audit.json`: audit counts and policy.
- `outputs/revenue_growth/rejected_rows.csv`: quarantined records, if any.
- `outputs/revenue_growth/monthly_growth.csv`, `city_growth.csv`, `channel_growth.csv`: analysis marts.
- `outputs/revenue_growth/index.html`: local interactive dashboard.

The generated files above are intentionally excluded from the repository. Re-run the scripts to recreate them.
