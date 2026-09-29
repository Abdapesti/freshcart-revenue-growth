"""Generate the FreshCart 360 relational synthetic dataset."""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw"


def write_csv(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if not rows:
        raise ValueError(f"No rows generated for {name}")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt, datetime) else dt.isoformat()


def weighted(rng, values, weights):
    return rng.choices(values, weights=weights, k=1)[0]


def main(seed: int, n_customers: int):
    rng = random.Random(seed)
    start, end = datetime(2024, 1, 1, 8), datetime(2025, 12, 31, 20)
    cities = ["Jakarta", "Bandung", "Surabaya", "Yogyakarta", "Medan"]
    channels = ["organic", "paid_social", "search", "referral", "partnership"]
    categories = ["Fresh Produce", "Dairy & Eggs", "Meat & Seafood", "Pantry", "Beverages", "Household", "Personal Care", "Frozen"]

    hubs = []
    hub_id = 1
    for city in cities:
        for suffix in range(1, 4):
            hubs.append({"hub_id": f"H{hub_id:03d}", "city": city, "hub_name": f"{city} Hub {suffix}", "capacity_orders_day": rng.randrange(300, 701, 50), "opened_date": iso(date(2023, 1, 1) + timedelta(days=rng.randint(0, 330)))})
            hub_id += 1

    products = []
    for i in range(1, 301):
        cat = categories[(i - 1) % len(categories)]
        base = rng.uniform(7000, 180000)
        products.append({"product_id": f"P{i:04d}", "category": cat, "product_name": f"{cat} Item {i:03d}", "unit_cost": round(base * rng.uniform(.58, .82), 2), "list_price": round(base, 2), "is_perishable": int(cat in {"Fresh Produce", "Dairy & Eggs", "Meat & Seafood", "Frozen"})})

    customers = []
    customer_traits = {}
    for i in range(1, n_customers + 1):
        signup = start + timedelta(days=rng.randint(0, 620), hours=rng.randint(0, 12))
        city = weighted(rng, cities, [42, 18, 17, 12, 11])
        income = weighted(rng, ["mass", "middle", "affluent"], [55, 33, 12])
        acquisition = weighted(rng, channels, [31, 25, 20, 15, 9])
        cid = f"C{i:06d}"
        customers.append({"customer_id": cid, "signup_at": iso(signup), "city": city, "acquisition_channel": acquisition, "income_segment": income, "is_subscription_member": int(rng.random() < {"mass": .10, "middle": .22, "affluent": .38}[income])})
        customer_traits[cid] = {"signup": signup, "city": city, "frequency": max(.15, rng.lognormvariate(-.15, .75))}

    orders, items, payments, deliveries, tickets, exposures = [], [], [], [], [], []
    order_seq = item_seq = ticket_seq = exposure_seq = 1
    city_hubs = {c: [h for h in hubs if h["city"] == c] for c in cities}
    campaign_names = ["WELCOME10", "PAYDAY", "WINBACK", "FREEDELIVERY"]

    for customer in customers:
        cid = customer["customer_id"]
        t = customer_traits[cid]
        active_days = max(1, (end - t["signup"]).days)
        expected = t["frequency"] * active_days / 35
        n_orders = min(80, max(0, int(rng.expovariate(1 / max(.6, expected)))))
        current = t["signup"] + timedelta(days=rng.randint(0, 10))
        experience_penalty = 1.0
        for _ in range(n_orders):
            gap = max(1, int(rng.expovariate(t["frequency"] / (24 * experience_penalty))))
            current += timedelta(days=gap, hours=rng.randint(0, 12), minutes=rng.randint(0, 59))
            if current > end:
                break
            oid = f"O{order_seq:08d}"
            order_seq += 1
            hub = rng.choice(city_hubs[t["city"]])
            n_items = weighted(rng, [1, 2, 3, 4, 5, 6, 7, 8], [7, 13, 20, 22, 17, 11, 7, 3])
            chosen = rng.sample(products, n_items)
            subtotal = 0.0
            item_rows = []
            substitution_count = 0
            for p in chosen:
                qty = weighted(rng, [1, 2, 3], [78, 18, 4])
                price = round(p["list_price"] * rng.uniform(.92, 1.04), 2)
                substituted = int(rng.random() < (.075 if p["is_perishable"] else .025))
                substitution_count += substituted
                subtotal += qty * price
                item_rows.append({"order_item_id": f"I{item_seq:09d}", "order_id": oid, "product_id": p["product_id"], "quantity": qty, "unit_price": price, "unit_cost": p["unit_cost"], "is_substituted": substituted})
                item_seq += 1
            discount = round(subtotal * weighted(rng, [0, .05, .10, .15, .20], [45, 15, 23, 12, 5]), 2)
            delivery_fee = 0 if customer["is_subscription_member"] or subtotal >= 250000 else weighted(rng, [9000, 12000, 15000], [45, 40, 15])
            service_fee = round(max(2000, subtotal * .012), 2)
            gross = round(subtotal - discount + delivery_fee + service_fee, 2)
            hour = current.hour
            peak = int(hour in {11, 12, 17, 18, 19, 20})
            cancel_prob = .025 + .025 * peak + .012 * substitution_count
            status = "cancelled" if rng.random() < cancel_prob else "completed"
            cancel_reason = weighted(rng, ["customer_request", "stockout", "payment_failed", "capacity"], [35, 30, 20, 15]) if status == "cancelled" else ""
            orders.append({"order_id": oid, "customer_id": cid, "hub_id": hub["hub_id"], "order_at": iso(current), "order_status": status, "cancel_reason": cancel_reason, "item_subtotal": round(subtotal, 2), "discount_amount": discount, "delivery_fee": delivery_fee, "service_fee": service_fee, "gross_amount": gross, "order_channel": weighted(rng, ["android", "ios", "web"], [58, 32, 10])})
            items.extend(item_rows)

            pay_status = "voided" if status == "cancelled" else "captured"
            refund_prob = .018 + .035 * (substitution_count > 0)
            refund = round(gross * rng.uniform(.10, .55), 2) if status == "completed" and rng.random() < refund_prob else 0
            payments.append({"payment_id": f"PAY{order_seq-1:08d}", "order_id": oid, "payment_method": weighted(rng, ["ewallet", "card", "bank_transfer", "cash"], [43, 27, 18, 12]), "payment_status": pay_status, "paid_amount": 0 if status == "cancelled" else gross, "refund_amount": refund, "paid_at": "" if status == "cancelled" else iso(current + timedelta(minutes=rng.randint(0, 4)))})

            if status == "completed":
                accepted = current + timedelta(minutes=rng.randint(1, 8))
                promised = current + timedelta(minutes=weighted(rng, [45, 60, 75, 90], [20, 45, 25, 10]))
                congestion = peak * rng.randint(8, 25)
                weather = int(rng.random() < .13)
                actual_minutes = max(25, int(rng.gauss(55 + congestion + 12 * weather + 5 * substitution_count, 13)))
                delivered = current + timedelta(minutes=actual_minutes)
                deliveries.append({"delivery_id": f"D{order_seq-1:08d}", "order_id": oid, "rider_id": f"R{rng.randint(1, 850):04d}", "accepted_at": iso(accepted), "promised_at": iso(promised), "delivered_at": iso(delivered), "distance_km": round(max(.4, rng.lognormvariate(1.0, .55)), 2), "weather_flag": weather, "delivery_minutes": actual_minutes, "is_late": int(delivered > promised)})
                late = delivered > promised
                ticket_prob = .018 + .11 * late + .055 * (substitution_count > 0) + .25 * (refund > 0)
                if rng.random() < ticket_prob:
                    created = delivered + timedelta(hours=rng.randint(0, 36))
                    issue = weighted(rng, ["late_delivery", "missing_item", "quality", "refund", "app_issue"], [36 if late else 10, 20, 19, 15, 10])
                    resolution_h = max(.5, rng.lognormvariate(1.7, .7))
                    tickets.append({"ticket_id": f"T{ticket_seq:08d}", "customer_id": cid, "order_id": oid, "created_at": iso(created), "issue_type": issue, "channel": weighted(rng, ["chat", "email", "phone"], [68, 20, 12]), "resolution_hours": round(resolution_h, 2), "csat_score": max(1, min(5, round(rng.gauss(4.25 - .75 * late - .45 * (resolution_h > 12), .75))))})
                    ticket_seq += 1
                # A poor experience increases the simulated delay before the next order.
                # This creates a learnable relationship, not causal evidence.
                experience_penalty = min(1.9, 1 + .30 * late + .18 * (substitution_count > 0) + .24 * (refund > 0))
            else:
                experience_penalty = 1.25
            if rng.random() < .20:
                sent = max(t["signup"], current - timedelta(days=rng.randint(1, 12), hours=rng.randint(0, 12)))
                clicked = rng.random() < .27
                exposures.append({"exposure_id": f"E{exposure_seq:08d}", "customer_id": cid, "campaign_name": rng.choice(campaign_names), "sent_at": iso(sent), "channel": weighted(rng, ["push", "email", "whatsapp"], [60, 24, 16]), "was_clicked": int(clicked), "assigned_variant": weighted(rng, ["control", "offer_a", "offer_b"], [20, 45, 35])})
                exposure_seq += 1

    counts = {}
    for name, rows in [("customers.csv", customers), ("hubs.csv", hubs), ("products.csv", products), ("orders.csv", orders), ("order_items.csv", items), ("payments.csv", payments), ("deliveries.csv", deliveries), ("support_tickets.csv", tickets), ("marketing_exposures.csv", exposures)]:
        counts[name] = write_csv(name, rows)
    print("FreshCart dataset generated")
    for k, v in counts.items():
        print(f"{k}: {v:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--customers", type=int, default=5000)
    args = parser.parse_args()
    main(args.seed, args.customers)
