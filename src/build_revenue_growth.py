"""Extract order data with SQL, audit/clean in Python, and build growth marts."""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "analytics" / "freshcart.sqlite"
OUT = ROOT / "outputs" / "revenue_growth"
NUMERIC = ("item_subtotal", "discount_amount", "refund_amount", "product_cost", "delivery_fee", "service_fee")


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def extract() -> list[dict]:
    with sqlite3.connect(DB) as connection:
        cursor = connection.execute((ROOT / "sql" / "revenue_growth_extract.sql").read_text(encoding="utf-8"))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor]


def clean(raw: list[dict]) -> tuple[list[dict], list[dict], dict]:
    cleaned, rejected, seen = [], [], set()
    reasons = defaultdict(int)
    for row in raw:
        errors = []
        order_id = str(row.get("order_id") or "").strip()
        if not order_id or order_id in seen:
            errors.append("missing_or_duplicate_order_id")
        seen.add(order_id)
        for field in ("customer_id", "city", "acquisition_channel"):
            if not str(row.get(field) or "").strip():
                errors.append(f"missing_{field}")
        try:
            order_at = datetime.fromisoformat(str(row["order_at"]))
            if order_at.strftime("%Y-%m") != row["order_month"]:
                errors.append("month_timestamp_mismatch")
        except (TypeError, ValueError):
            errors.append("invalid_order_at")
        status = row.get("order_status")
        if status not in {"completed", "cancelled"}:
            errors.append("invalid_order_status")
        amounts = {}
        for field in NUMERIC:
            try:
                value = float(row[field])
                if not math.isfinite(value) or value < 0:
                    raise ValueError
                amounts[field] = round(value, 2)
            except (TypeError, ValueError):
                errors.append(f"invalid_{field}")
        if not errors:
            if amounts["discount_amount"] > amounts["item_subtotal"]:
                errors.append("discount_exceeds_subtotal")
            if row["is_first_completed_order"] not in (0, 1):
                errors.append("invalid_first_order_flag")
            if status != "completed" and row["is_first_completed_order"]:
                errors.append("cancelled_marked_first_order")
        if errors:
            for reason in set(errors):
                reasons[reason] += 1
            rejected.append({"order_id": order_id, "reasons": "|".join(sorted(set(errors)))})
            continue
        record = {**row, **amounts, "order_id": order_id}
        record["net_sales_idr"] = round(amounts["item_subtotal"] - amounts["discount_amount"] - amounts["refund_amount"], 2)
        record["contribution_proxy_idr"] = round(record["net_sales_idr"] - amounts["product_cost"] + amounts["delivery_fee"] + amounts["service_fee"], 2)
        cleaned.append(record)
    audit = {
        "source": "SQLite fact_orders via sql/revenue_growth_extract.sql",
        "raw_rows": len(raw), "clean_rows": len(cleaned), "rejected_rows": len(rejected),
        "rejection_reasons": dict(sorted(reasons.items())),
        "policy": "Trim ID; parse timestamp and money; reject invalid rows rather than silently imputing revenue; round monetary fields to 2 decimals.",
        "note": "Synthetic source is already clean; zero rejected rows is expected and does not demonstrate fixing real-world errors.",
    }
    return cleaned, rejected, audit


def marts(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    grouped = defaultdict(lambda: {"completed_orders": 0, "new_customer_orders": 0, "gmv_idr": 0.0, "net_sales_idr": 0.0, "contribution_proxy_idr": 0.0, "customers": set()})
    for row in rows:
        if row["order_status"] != "completed":
            continue
        for grain in (("month", row["order_month"]), ("city", row["order_month"], row["city"]), ("channel", row["order_month"], row["acquisition_channel"])):
            bucket = grouped[grain]
            bucket["completed_orders"] += 1
            bucket["new_customer_orders"] += row["is_first_completed_order"]
            bucket["customers"].add(row["customer_id"])
            for field in ("gmv_idr", "net_sales_idr", "contribution_proxy_idr"):
                source = "item_subtotal" if field == "gmv_idr" else field
                bucket[field] += row[source]
    outputs = {"month": [], "city": [], "channel": []}
    for key, bucket in sorted(grouped.items()):
        kind, month, *segment = key
        result = {"month": month}
        if segment:
            result["segment"] = segment[0]
        result.update({
            "completed_orders": bucket["completed_orders"],
            "new_customer_orders": bucket["new_customer_orders"],
            "returning_customer_orders": bucket["completed_orders"] - bucket["new_customer_orders"],
            "active_customers": len(bucket["customers"]),
            "gmv_idr": round(bucket["gmv_idr"], 2),
            "net_sales_idr": round(bucket["net_sales_idr"], 2),
            "contribution_proxy_idr": round(bucket["contribution_proxy_idr"], 2),
        })
        outputs[kind].append(result)
    return outputs["month"], outputs["city"], outputs["channel"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = extract()
    write_csv(OUT / "sql_extract.csv", raw, list(raw[0]))
    cleaned, rejected, audit = clean(raw)
    write_csv(OUT / "clean_orders.csv", cleaned, list(cleaned[0]))
    write_csv(OUT / "rejected_rows.csv", rejected, ["order_id", "reasons"])
    (OUT / "cleaning_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    if rejected:
        raise ValueError(f"{len(rejected)} invalid orders quarantined; inspect rejected_rows.csv before publishing marts")
    monthly, city, channel = marts(cleaned)
    fields = ["month", "completed_orders", "new_customer_orders", "returning_customer_orders", "active_customers", "gmv_idr", "net_sales_idr", "contribution_proxy_idr"]
    write_csv(OUT / "monthly_growth.csv", monthly, fields)
    write_csv(OUT / "city_growth.csv", city, ["month", "segment", *fields[1:]])
    write_csv(OUT / "channel_growth.csv", channel, ["month", "segment", *fields[1:]])
    payload = {"monthly": monthly, "city": city, "channel": channel}
    template = (ROOT / "src" / "revenue_growth_template.html").read_text(encoding="utf-8")
    (OUT / "index.html").write_text(template.replace("/*__GROWTH_DATA__*/", "const DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";"), encoding="utf-8")
    print(f"SQL extracted {len(raw):,}; clean {len(cleaned):,}; rejected {len(rejected):,}; monthly periods {len(monthly)}")


if __name__ == "__main__":
    main()
