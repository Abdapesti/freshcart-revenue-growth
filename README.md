# FreshCart 360: Revenue & Growth Analysis

An end-to-end analytics portfolio case study using **SQL, Python, and an interactive web dashboard**. FreshCart is a fictional grocery delivery business operating across five Indonesian cities. Every record is synthetic; the project contains no real customer or company data.

[View the six-slide case study (PDF)](case-study/FreshCart_Revenue_Growth_Case_Study.pdf)

## Business question

How did monthly sales and completed orders change from 2024 to 2025? How much order volume came from first purchases, and which cities contributed most to gross merchandise value (GMV)? The analysis is intended to identify follow-up questions, not establish the cause of growth.

## What the project does

1. Generates nine related CSV tables with a fixed random seed.
2. Loads the tables into SQLite and builds order-level KPI views. Line items are aggregated before joining to orders to prevent duplicate revenue.
3. Extracts one row per order with SQL, including a flag for each customer's first completed purchase.
4. Audits the extract in Python. Invalid records are quarantined, and the pipeline stops before publishing marts if any are found.
5. Builds monthly, city, and acquisition-channel marts plus a local interactive dashboard.
6. Reconciles SQL and Python totals with automated tests.

## Key results from the synthetic dataset

| Metric | 2025 result |
| --- | ---: |
| Completed orders | 27,644 |
| GMV | Rp12.95 billion |
| Net sales | Rp12.09 billion |
| First-purchase orders | 1,960 |
| Jakarta share of GMV | About 43.8% |

The pipeline audits 44,472 orders across 24 months. All rows pass validation because the generated source data is already clean. The cleaning tests also inject invalid examples to verify that the rejection rules work.

## Reproduce the analysis

Requires Python 3.10 or later. The pipeline uses only the Python standard library.

```powershell
python src/generate_data.py --seed 42 --customers 5000
python tests/validate_data.py
python src/build_analytics.py
python tests/validate_analytics.py
python src/build_revenue_growth.py
python tests/validate_revenue_growth.py
```

Generated CSVs, the SQLite database, and analysis outputs are written to `data/` and `outputs/`; they are excluded from version control. Open `outputs/revenue_growth/index.html` locally to explore the charts. The PDF linked above is the concise recruiter-facing output.

## Metric definitions

| Metric | Definition |
| --- | --- |
| Completed orders | Orders with `order_status = completed`. |
| GMV | Sum of `item_subtotal` on completed orders, before discounts and fees. |
| Net sales | GMV minus order discounts and refunds. This is not profit. |
| First-purchase orders | Each customer's first completed order, ordered by timestamp and `order_id`. |
| Subsequent orders | Completed orders other than the first purchase. This counts orders, not unique returning customers. |
| Contribution proxy | Net sales minus product cost, plus delivery and service fees. Rider, payment, overhead, and campaign costs are excluded. |

## Repository structure

```text
case-study/  Six-slide PDF summary
docs/        Data dictionary and methodology
sql/         SQLite schema, KPI views, and analysis extract
src/         Synthetic generator, database build, audit, marts, and dashboard template
tests/       Integrity checks and SQL/Python reconciliations
```

## Limitations

- The source is synthetic and already clean. Zero rejected rows should not be presented as evidence of cleaning a messy real-world dataset.
- Late-2025 trends are influenced by the generator stopping new-customer acquisition near the end of the period. The charts cannot identify the cause of a decline.
- The work is descriptive. Promotion impact would require a controlled experiment or a suitable causal design.
- Generated row-level data and the SQLite database are intentionally not committed. The scripts reproduce them with seed `42`.

See [the methodology](docs/06_revenue_growth_portfolio.md) for the full pipeline and validation decisions.
