"""Fail-fast integrity checks for generated FreshCart CSV files."""
import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"


def load(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def unique(rows, key):
    values = [r[key] for r in rows]
    assert len(values) == len(set(values)), f"Duplicate {key}"


def dt(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


customers, hubs, products = load("customers.csv"), load("hubs.csv"), load("products.csv")
orders, items, payments = load("orders.csv"), load("order_items.csv"), load("payments.csv")
deliveries, tickets, exposures = load("deliveries.csv"), load("support_tickets.csv"), load("marketing_exposures.csv")

for rows, key in [(customers, "customer_id"), (hubs, "hub_id"), (products, "product_id"), (orders, "order_id"), (items, "order_item_id"), (payments, "payment_id"), (deliveries, "delivery_id"), (tickets, "ticket_id"), (exposures, "exposure_id")]:
    unique(rows, key)

customer_ids, hub_ids, product_ids, order_ids = {r["customer_id"] for r in customers}, {r["hub_id"] for r in hubs}, {r["product_id"] for r in products}, {r["order_id"] for r in orders}
assert all(r["customer_id"] in customer_ids and r["hub_id"] in hub_ids for r in orders)
assert all(r["order_id"] in order_ids and r["product_id"] in product_ids for r in items)
assert all(r["order_id"] in order_ids for r in payments + deliveries)
assert all(r["customer_id"] in customer_ids and r["order_id"] in order_ids for r in tickets)
assert all(r["customer_id"] in customer_ids for r in exposures)

order_map = {r["order_id"]: r for r in orders}
item_sum = {}
for r in items:
    item_sum[r["order_id"]] = item_sum.get(r["order_id"], 0) + int(r["quantity"]) * float(r["unit_price"])
for oid, order in order_map.items():
    assert abs(item_sum[oid] - float(order["item_subtotal"])) < .011, f"Subtotal mismatch {oid}"
    expected = float(order["item_subtotal"]) - float(order["discount_amount"]) + float(order["delivery_fee"]) + float(order["service_fee"])
    assert abs(expected - float(order["gross_amount"])) < .02, f"Gross mismatch {oid}"
    assert order["order_status"] in {"completed", "cancelled"}

for r in deliveries:
    o = order_map[r["order_id"]]
    assert o["order_status"] == "completed"
    assert dt(o["order_at"]) <= dt(r["accepted_at"]) <= dt(r["delivered_at"])
for r in tickets:
    assert dt(r["created_at"]) >= dt(order_map[r["order_id"]]["order_at"])
for r in payments:
    assert float(r["refund_amount"]) >= 0 and float(r["refund_amount"]) <= float(r["paid_amount"])
    o = order_map[r["order_id"]]
    assert (r["payment_status"] == "captured") == (o["order_status"] == "completed")
    assert abs(float(r["paid_amount"]) - (float(o["gross_amount"]) if o["order_status"] == "completed" else 0)) < .011

signup_at = {r["customer_id"]: dt(r["signup_at"]) for r in customers}
assert all(dt(r["sent_at"]) >= signup_at[r["customer_id"]] for r in exposures)
assert len(payments) == len(orders)
assert len(deliveries) == sum(r["order_status"] == "completed" for r in orders)

print(f"PASS: 9 tables, {len(orders):,} orders, all integrity checks passed")
