"""Load FreshCart CSVs into SQLite and export reproducible BI marts."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB_DIR = ROOT / "data" / "analytics"
DB_PATH = DB_DIR / "freshcart.sqlite"
MART_DIR = ROOT / "outputs" / "marts"

TABLES = (
    "customers", "hubs", "products", "orders", "order_items", "payments",
    "deliveries", "support_tickets", "marketing_exposures",
)
EXPORTS = (
    ("monthly_business_kpis", "monthly_business_kpis.csv"),
    ("monthly_delivery_kpis", "monthly_delivery_kpis.csv"),
    ("cohort_30d", "cohort_30d.csv"),
    ("city_monthly_kpis", "city_monthly_kpis.csv"),
    ("cohort_city_30d", "cohort_city_30d.csv"),
    ("hub_monthly_kpis", "hub_monthly_kpis.csv"),
)


def load_table(connection: sqlite3.Connection, table: str) -> int:
    with (RAW / f"{table}.csv").open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        columns = reader.fieldnames
        if not columns:
            raise ValueError(f"CSV without header: {table}")
        quoted = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join("?" for _ in columns)
        statement = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
        total = 0
        batch = []
        for row in reader:
            batch.append(tuple(None if row[col] == "" else row[col] for col in columns))
            if len(batch) == 2000:
                connection.executemany(statement, batch)
                total += len(batch)
                batch.clear()
        if batch:
            connection.executemany(statement, batch)
            total += len(batch)
        return total


def export_view(connection: sqlite3.Connection, view: str, filename: str) -> int:
    MART_DIR.mkdir(parents=True, exist_ok=True)
    cursor = connection.execute(f'SELECT * FROM "{view}" ORDER BY 1, 2')
    with (MART_DIR / filename).open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow([column[0] for column in cursor.description])
        count = 0
        for row in cursor:
            writer.writerow(row)
            count += 1
    return count


def main() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    # Rebuild into a sibling file, then replace the managed database atomically.
    pending = DB_DIR / "freshcart.pending.sqlite"
    if pending.exists():
        pending.unlink()
    connection = sqlite3.connect(pending)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        for table in TABLES:
            print(f"Loaded {table}: {load_table(connection, table):,}")
        connection.commit()
        connection.executescript((ROOT / "sql" / "kpi_views_sqlite.sql").read_text(encoding="utf-8"))
        connection.commit()
        problems = connection.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise AssertionError(f"Foreign key errors: {problems[:5]}")
        for view, filename in EXPORTS:
            print(f"Exported {filename}: {export_view(connection, view, filename):,} rows")
    finally:
        connection.close()
    pending.replace(DB_PATH)
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
