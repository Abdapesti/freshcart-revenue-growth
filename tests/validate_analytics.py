"""Reconcile SQL marts to independent calculations from raw CSV."""
import csv
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "analytics" / "freshcart.sqlite"


def read(name):
    with (ROOT / "data" / "raw" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


orders = read("orders")
payments = {r["order_id"]: r for r in read("payments")}
deliveries = {r["order_id"]: r for r in read("deliveries")}
costs = defaultdict(float)
for row in read("order_items"):
    costs[row["order_id"]] += int(row["quantity"]) * float(row["unit_cost"])
tickets = {r["order_id"] for r in read("support_tickets")}
monthly = defaultdict(lambda: {"submitted": 0, "completed": 0, "gmv": 0.0, "net_sales": 0.0, "contribution": 0.0, "late": 0, "contact": 0, "customers": set()})
completed_by_customer = defaultdict(list)
for order in orders:
    m = monthly[order["order_at"][:7]]
    m["submitted"] += 1
    if order["order_status"] != "completed":
        continue
    m["completed"] += 1
    m["customers"].add(order["customer_id"])
    m["gmv"] += float(order["item_subtotal"])
    net = float(order["item_subtotal"]) - float(order["discount_amount"]) - float(payments[order["order_id"]]["refund_amount"])
    m["net_sales"] += net
    m["contribution"] += net - costs[order["order_id"]] + float(order["delivery_fee"]) + float(order["service_fee"])
    m["late"] += int(deliveries[order["order_id"]]["is_late"])
    m["contact"] += order["order_id"] in tickets
    completed_by_customer[order["customer_id"]].append(datetime.fromisoformat(order["order_at"]))

with sqlite3.connect(DB) as db:
    assert db.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0] == len(orders)
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    db.row_factory = sqlite3.Row
    for row in db.execute("SELECT * FROM monthly_business_kpis"):
        m = monthly[row["month"]]
        assert row["submitted_orders"] == m["submitted"]
        assert row["completed_orders"] == m["completed"]
        assert row["monthly_active_customers"] == len(m["customers"])
        assert abs(row["gmv_idr"] - m["gmv"]) < .02
        assert abs(row["net_sales_idr"] - m["net_sales"]) < .02
        assert abs(row["contribution_proxy_idr"] - m["contribution"]) < .02
        assert abs(row["on_time_rate"] - (1 - m["late"] / m["completed"])) < .000051
        assert abs(row["contact_rate"] - (m["contact"] / m["completed"])) < .000051
    cohort = defaultdict(lambda: [0, 0])
    for dates in completed_by_customer.values():
        dates.sort()
        first = dates[0]
        if first.strftime("%Y-%m") == "2025-12":
            continue  # December cohort lacks a full 30-day follow-up.
        month = first.strftime("%Y-%m")
        cohort[month][0] += 1
        cohort[month][1] += len(dates) > 1 and dates[1] <= first + timedelta(days=30)
    for row in db.execute("SELECT * FROM cohort_30d"):
        expected = cohort[row["cohort_month"]]
        assert row["acquired_customers"] == expected[0]
        assert row["repeat_customers_30d"] == expected[1]
    for row in db.execute("""
        SELECT m.month, m.submitted_orders AS all_submitted,
               SUM(c.submitted_orders) AS city_submitted,
               m.completed_orders AS all_completed,
               SUM(c.completed_orders) AS city_completed,
               m.gmv_idr AS all_gmv, SUM(c.gmv_idr) AS city_gmv,
               SUM(c.on_time_orders) AS on_time_orders,
               SUM(c.contact_orders) AS contact_orders
        FROM monthly_business_kpis m JOIN city_monthly_kpis c ON c.month = m.month
        GROUP BY m.month
    """):
        m = monthly[row["month"]]
        assert row["all_submitted"] == row["city_submitted"]
        assert row["all_completed"] == row["city_completed"]
        assert abs(row["all_gmv"] - row["city_gmv"]) < .02
        assert row["on_time_orders"] == m["completed"] - m["late"]
        assert row["contact_orders"] == m["contact"]
    for row in db.execute("""
        SELECT a.cohort_month, a.acquired_customers, a.repeat_customers_30d,
               SUM(c.acquired_customers) AS city_acquired,
               SUM(c.repeat_customers_30d) AS city_repeat
        FROM cohort_30d a JOIN cohort_city_30d c ON c.cohort_month = a.cohort_month
        GROUP BY a.cohort_month
    """):
        assert row["acquired_customers"] == row["city_acquired"]
        assert row["repeat_customers_30d"] == row["city_repeat"]
    for row in db.execute("""
        SELECT c.month, c.city, c.completed_orders AS city_completed,
               SUM(h.completed_orders) AS hub_completed,
               c.on_time_orders AS city_on_time, SUM(h.on_time_orders) AS hub_on_time
        FROM city_monthly_kpis c JOIN hub_monthly_kpis h
          ON h.month = c.month AND h.city = c.city
        GROUP BY c.month, c.city
    """):
        assert row["city_completed"] == row["hub_completed"]
        assert row["city_on_time"] == row["hub_on_time"]

print(f"PASS: {len(monthly)} monthly KPI rows and cohort counts reconcile to raw CSV")
