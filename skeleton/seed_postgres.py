"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import os
import sys

import psycopg2
from argon2 import PasswordHasher
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    # All seeders use ON CONFLICT DO NOTHING so the script is idempotent:
    # teammates and TAs can safely re-run it after a reset or pull without
    # creating duplicate rows or failing on primary-key collisions.
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


def split_name(full_name):
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], " ".join(parts[1:])


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    columns = [
        "station_id",
        "name",
        "lines",
        "is_interchange_metro",
        "interchange_metro_lines",
        "is_interchange_national_rail",
        "interchange_national_rail_station_id",
    ]
    rows = [
        (
            item["station_id"],
            item["name"],
            item["lines"],
            item["is_interchange_metro"],
            item.get("interchange_metro_lines", []),
            item["is_interchange_national_rail"],
            item.get("interchange_national_rail_station_id"),
        )
        for item in data
    ]
    inserted = insert_many(cur, "metro_stations", columns, rows)
    print(f"  metro_stations: {inserted} inserted")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    columns = [
        "station_id",
        "name",
        "lines",
        "is_interchange_national_rail",
        "interchange_national_rail_lines",
        "is_interchange_metro",
        "interchange_metro_station_id",
    ]
    rows = [
        (
            item["station_id"],
            item["name"],
            item["lines"],
            item["is_interchange_national_rail"],
            item.get("interchange_national_rail_lines", []),
            item["is_interchange_metro"],
            item.get("interchange_metro_station_id"),
        )
        for item in data
    ]
    inserted = insert_many(cur, "national_rail_stations", columns, rows)
    print(f"  national_rail_stations: {inserted} inserted")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    columns = [
        "schedule_id",
        "line",
        "direction",
        "origin_station_id",
        "destination_station_id",
        "first_train_time",
        "last_train_time",
        "base_fare_usd",
        "per_stop_rate_usd",
        "frequency_min",
        "operates_on",
    ]
    rows = []
    stop_rows = []
    for item in data:
        rows.append(
            (
                item["schedule_id"],
                item["line"],
                item["direction"],
                item["origin_station_id"],
                item["destination_station_id"],
                item["first_train_time"],
                item["last_train_time"],
                item["base_fare_usd"],
                item["per_stop_rate_usd"],
                item["frequency_min"],
                item["operates_on"],
            )
        )
        travel_times = item["travel_time_from_origin_min"]
        # The raw JSON stores stop order as an array, but the relational schema
        # stores one row per stop. This keeps schedules in 3NF and lets queries
        # compare origin/destination stop_order without parsing JSON in SQL.
        for stop_order, station_id in enumerate(item["stops_in_order"], start=1):
            stop_rows.append(
                (
                    item["schedule_id"],
                    station_id,
                    stop_order,
                    travel_times[station_id],
                )
            )
    inserted = insert_many(cur, "metro_schedules", columns, rows)
    inserted_stops = insert_many(
        cur,
        "metro_schedule_stops",
        ["schedule_id", "station_id", "stop_order", "travel_time_from_origin_min"],
        stop_rows,
    )
    print(f"  metro_schedules: {inserted} inserted")
    print(f"  metro_schedule_stops: {inserted_stops} inserted")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    schedule_columns = [
        "schedule_id",
        "line",
        "service_type",
        "direction",
        "origin_station_id",
        "destination_station_id",
        "first_train_time",
        "last_train_time",
        "frequency_min",
        "operates_on",
    ]
    schedule_rows = []
    stop_rows = []
    fare_rows = []
    for item in data:
        schedule_rows.append(
            (
                item["schedule_id"],
                item["line"],
                item["service_type"],
                item["direction"],
                item["origin_station_id"],
                item["destination_station_id"],
                item["first_train_time"],
                item["last_train_time"],
                item["frequency_min"],
                item["operates_on"],
            )
        )
        travel_times = item["travel_time_from_origin_min"]
        passed_through = set(item.get("passed_through_stations", []))
        # Express services may pass through stations without stopping. We keep
        # that as an explicit boolean property on the stop row so route and
        # timetable queries can distinguish served stops from pass-through data.
        for stop_order, station_id in enumerate(item["stops_in_order"], start=1):
            stop_rows.append(
                (
                    item["schedule_id"],
                    station_id,
                    stop_order,
                    travel_times[station_id],
                    station_id in passed_through,
                )
            )
        for fare_class, fare in item.get("fare_classes", {}).items():
            fare_rows.append(
                (
                    item["schedule_id"],
                    fare_class,
                    fare["base_fare_usd"],
                    fare["per_stop_rate_usd"],
                )
            )

    inserted_schedules = insert_many(
        cur,
        "national_rail_schedules",
        schedule_columns,
        schedule_rows,
    )
    inserted_fares = insert_many(
        cur,
        "national_rail_fares",
        ["schedule_id", "fare_class", "base_fare_usd", "per_stop_rate_usd"],
        fare_rows,
    )
    inserted_stops = insert_many(
        cur,
        "national_rail_schedule_stops",
        [
            "schedule_id",
            "station_id",
            "stop_order",
            "travel_time_from_origin_min",
            "is_passed_through",
        ],
        stop_rows,
    )
    print(f"  national_rail_schedules: {inserted_schedules} inserted")
    print(f"  national_rail_fares: {inserted_fares} inserted")
    print(f"  national_rail_schedule_stops: {inserted_stops} inserted")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    layout_rows = []
    seat_rows = []
    for item in data:
        layout_rows.append((item["layout_id"], item["schedule_id"]))
        # Seat layouts are decomposed into individual seat rows because booking
        # availability is checked at seat granularity, not at whole-coach level.
        for coach in item.get("coaches", []):
            for seat in coach.get("seats", []):
                seat_rows.append(
                    (
                        item["layout_id"],
                        item["schedule_id"],
                        coach["coach"],
                        coach["fare_class"],
                        seat["seat_id"],
                        seat["row"],
                        seat["column"],
                    )
                )

    inserted_layouts = insert_many(
        cur,
        "national_rail_seat_layouts",
        ["layout_id", "schedule_id"],
        layout_rows,
    )
    inserted_seats = insert_many(
        cur,
        "national_rail_seats",
        [
            "layout_id",
            "schedule_id",
            "coach",
            "fare_class",
            "seat_id",
            "row_number",
            "seat_column",
        ],
        seat_rows,
    )
    print(f"  national_rail_seat_layouts: {inserted_layouts} inserted")
    print(f"  national_rail_seats: {inserted_seats} inserted")


def seed_users(cur):
    data = load("registered_users.json")
    hasher = PasswordHasher()
    user_rows = []
    credential_rows = []
    for item in data:
        first_name, surname = split_name(item["full_name"])
        user_rows.append(
            (
                item["user_id"],
                item["full_name"],
                first_name,
                surname,
                item["email"],
                item.get("phone"),
                item.get("date_of_birth"),
                item["secret_question"],
                item["secret_answer"],
                item["registered_at"],
                item.get("is_active", True),
            )
        )
        credential_rows.append(
            (
                item["user_id"],
                # Passwords from the mock JSON are never stored directly.
                # Argon2 hashes include their own salt and cost parameters,
                # which protects users even if the credentials table leaks.
                hasher.hash(item["password"]),
                item["registered_at"],
            )
        )

    inserted_users = insert_many(
        cur,
        "registered_users",
        [
            "user_id",
            "full_name",
            "first_name",
            "surname",
            "email",
            "phone",
            "date_of_birth",
            "secret_question",
            "secret_answer",
            "registered_at",
            "is_active",
        ],
        user_rows,
    )
    inserted_credentials = insert_many(
        cur,
        "user_password_credentials",
        ["user_id", "password_hash", "password_updated_at"],
        credential_rows,
    )
    print(f"  registered_users: {inserted_users} inserted")
    print(f"  user_password_credentials: {inserted_credentials} inserted")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    columns = [
        "booking_id",
        "user_id",
        "schedule_id",
        "origin_station_id",
        "destination_station_id",
        "travel_date",
        "departure_time",
        "ticket_type",
        "fare_class",
        "coach",
        "seat_id",
        "stops_travelled",
        "amount_usd",
        "status",
        "booked_at",
        "travelled_at",
    ]
    rows = [
        (
            item["booking_id"],
            item["user_id"],
            item["schedule_id"],
            item["origin_station_id"],
            item["destination_station_id"],
            item["travel_date"],
            item["departure_time"],
            item["ticket_type"],
            item["fare_class"],
            item.get("coach"),
            item.get("seat_id"),
            item["stops_travelled"],
            item["amount_usd"],
            item["status"],
            item["booked_at"],
            item.get("travelled_at"),
        )
        for item in data
    ]
    inserted = insert_many(cur, "national_rail_bookings", columns, rows)
    print(f"  national_rail_bookings: {inserted} inserted")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    columns = [
        "trip_id",
        "user_id",
        "schedule_id",
        "origin_station_id",
        "destination_station_id",
        "travel_date",
        "ticket_type",
        "day_pass_ref",
        "stops_travelled",
        "amount_usd",
        "status",
        "purchased_at",
        "travelled_at",
    ]
    rows = [
        (
            item["trip_id"],
            item["user_id"],
            item["schedule_id"],
            item["origin_station_id"],
            item["destination_station_id"],
            item["travel_date"],
            item["ticket_type"],
            item.get("day_pass_ref"),
            item.get("stops_travelled"),
            item["amount_usd"],
            item["status"],
            item.get("purchased_at"),
            item.get("travelled_at"),
        )
        for item in data
    ]
    inserted = insert_many(cur, "metro_travels", columns, rows)
    print(f"  metro_travels: {inserted} inserted")


def seed_payments(cur):
    data = load("payments.json")
    columns = [
        "payment_id",
        "booking_id",
        "trip_id",
        "amount_usd",
        "method",
        "status",
        "paid_at",
    ]
    rows = [
        (
            item["payment_id"],
            # Source data uses one "booking_id" field for both national rail
            # bookings (BK...) and metro trips (MT...). The schema splits them
            # into nullable FKs so each payment still has real referential
            # integrity instead of a loose polymorphic text reference.
            item["booking_id"] if item["booking_id"].startswith("BK") else None,
            item["booking_id"] if item["booking_id"].startswith("MT") else None,
            item["amount_usd"],
            item["method"],
            item["status"],
            item["paid_at"],
        )
        for item in data
    ]
    inserted = insert_many(cur, "payments", columns, rows)
    print(f"  payments: {inserted} inserted")


def seed_feedback(cur):
    data = load("feedback.json")
    columns = [
        "feedback_id",
        "booking_id",
        "trip_id",
        "user_id",
        "rating",
        "comment",
        "submitted_at",
    ]
    rows = [
        (
            item["feedback_id"],
            # Feedback follows the same BK/MT split as payments: exactly one of
            # booking_id or trip_id is populated, matching the schema CHECK.
            item["booking_id"] if item["booking_id"].startswith("BK") else None,
            item["booking_id"] if item["booking_id"].startswith("MT") else None,
            item["user_id"],
            item["rating"],
            item.get("comment"),
            item["submitted_at"],
        )
        for item in data
    ]
    inserted = insert_many(cur, "feedback", columns, rows)
    print(f"  feedback: {inserted} inserted")


def verify_counts(cur):
    tables = [
        "metro_stations",
        "national_rail_stations",
        "metro_schedules",
        "national_rail_schedules",
        "national_rail_schedule_stops",
        "national_rail_fares",
        "metro_schedule_stops",
        "national_rail_seat_layouts",
        "national_rail_seats",
        "registered_users",
        "user_password_credentials",
        "national_rail_bookings",
        "metro_travels",
        "payments",
        "feedback",
    ]
    print("\nRow counts:")
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        # The order follows foreign-key dependencies: parent reference tables
        # first, then schedules/stops/fares/seats/users, then transactions and
        # feedback. One transaction wraps the whole seed so a failure leaves the
        # database unchanged instead of half-populated.
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
        verify_counts(cur)
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
