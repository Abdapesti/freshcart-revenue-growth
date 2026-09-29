"""Independent reconciliation for the Revenue & Growth portfolio view."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "revenue_growth"
sys.path.insert(0, str(ROOT / "src"))
from build_revenue_growth import clean as clean_orders  # noqa: E402


def read(name):
    with (OUT / name).open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def near(a, b):
    assert abs(float(a) - float(b)) < 0.02, (a, b)


def main():
    audit = json.loads((OUT / "cleaning_audit.json").read_text(encoding="utf-8"))
    raw, clean, monthly, city, channel = map(read, ("sql_extract.csv", "clean_orders.csv", "monthly_growth.csv", "city_growth.csv", "channel_growth.csv"))
    assert audit["raw_rows"] == len(raw) == 44472
    assert audit["clean_rows"] == len(clean) == 44472
    assert audit["rejected_rows"] == len(read("rejected_rows.csv")) == 0
    assert len({r["order_id"] for r in clean}) == len(clean)
    sample = dict(raw[0], is_first_completed_order=int(raw[0]["is_first_completed_order"]))
    duplicate = dict(sample)
    negative = dict(sample, order_id="BAD-NEGATIVE", item_subtotal=-1)
    kept, quarantined, test_audit = clean_orders([sample, duplicate, negative])
    assert len(kept) == 1 and len(quarantined) == 2
    assert test_audit["rejection_reasons"] == {"invalid_item_subtotal": 1, "missing_or_duplicate_order_id": 1}
    assert len(monthly) == 24
    with sqlite3.connect(ROOT / "data" / "analytics" / "freshcart.sqlite") as db:
        reference = {r[0]: r for r in db.execute("SELECT month, completed_orders, gmv_idr, net_sales_idr FROM monthly_business_kpis")}
        unique_completed_customers = db.execute("SELECT COUNT(DISTINCT customer_id) FROM orders WHERE order_status='completed'").fetchone()[0]
    assert sum(int(r["new_customer_orders"]) for r in monthly) == unique_completed_customers
    for row in monthly:
        month = row["month"]
        assert int(row["completed_orders"]) == reference[month][1]
        near(row["gmv_idr"], reference[month][2])
        near(row["net_sales_idr"], reference[month][3])
        for segment in (city, channel):
            subset = [r for r in segment if r["month"] == month]
            assert sum(int(r["completed_orders"]) for r in subset) == int(row["completed_orders"])
            near(sum(float(r["gmv_idr"]) for r in subset), row["gmv_idr"])
    html = (OUT / "index.html").read_text(encoding="utf-8")
    assert "/*__GROWTH_DATA__*/" not in html and "Data sintetis" in html
    print("PASS: SQL/Python growth marts reconcile with independent KPI view, cities, and channels")


if __name__ == "__main__":
    main()
