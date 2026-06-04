"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Optional

import psycopg2
import psycopg2.extras
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


_PASSWORD_HASHER = PasswordHasher(type=Type.ID)


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        travel_date:     e.g. "2025-06-01" — used to count bookings; omit for general info

    Returns:
        List of matching schedules with stop count, travel time, and seat counts.
    """
    sql = """
        WITH matching_schedules AS (
            SELECT
                s.*,
                origin_stop.stop_order AS origin_stop_order,
                destination_stop.stop_order AS destination_stop_order,
                origin_stop.travel_time_from_origin_min AS origin_time_min,
                destination_stop.travel_time_from_origin_min AS destination_time_min
            FROM national_rail_schedules s
            JOIN national_rail_schedule_stops origin_stop
                ON origin_stop.schedule_id = s.schedule_id
               AND origin_stop.station_id = %s
            JOIN national_rail_schedule_stops destination_stop
                ON destination_stop.schedule_id = s.schedule_id
               AND destination_stop.station_id = %s
            WHERE origin_stop.stop_order < destination_stop.stop_order
              AND (
                  %s::DATE IS NULL
                  OR lower(trim(to_char(%s::DATE, 'dy'))) = ANY (s.operates_on)
              )
        )
        SELECT
            s.schedule_id,
            s.line,
            s.service_type,
            s.direction,
            s.origin_station_id AS schedule_origin_station_id,
            s.destination_station_id AS schedule_destination_station_id,
            stop_lists.stops_in_order,
            stop_lists.passed_through_stations,
            s.first_train_time,
            s.last_train_time,
            s.frequency_min,
            s.operates_on,
            %s::VARCHAR AS requested_origin_id,
            %s::VARCHAR AS requested_destination_id,
            origin_station.name AS origin_name,
            destination_station.name AS destination_name,
            s.origin_stop_order,
            s.destination_stop_order,
            (s.destination_stop_order - s.origin_stop_order)::INTEGER AS stops_travelled,
            (s.destination_time_min - s.origin_time_min)::INTEGER AS travel_time_min,
            COALESCE(seat_counts.total_seats, 0)::INTEGER AS total_seats,
            COUNT(b.booking_id)::INTEGER AS booked_seats,
            (COALESCE(seat_counts.total_seats, 0) - COUNT(b.booking_id))::INTEGER
                AS available_seats
        FROM matching_schedules s
        JOIN national_rail_stations origin_station
            ON origin_station.station_id = %s
        JOIN national_rail_stations destination_station
            ON destination_station.station_id = %s
        JOIN LATERAL (
            SELECT
                array_agg(station_id ORDER BY stop_order) AS stops_in_order,
                array_agg(station_id ORDER BY stop_order)
                    FILTER (WHERE is_passed_through) AS passed_through_stations
            FROM national_rail_schedule_stops stops
            WHERE stops.schedule_id = s.schedule_id
        ) stop_lists ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::INTEGER AS total_seats
            FROM national_rail_seats seats
            WHERE seats.schedule_id = s.schedule_id
        ) seat_counts ON TRUE
        LEFT JOIN national_rail_bookings b
            ON b.schedule_id = s.schedule_id
            AND %s::DATE IS NOT NULL
            AND b.travel_date = %s::DATE
            AND b.status <> 'cancelled'
        GROUP BY
            s.schedule_id,
            s.line,
            s.service_type,
            s.direction,
            s.origin_station_id,
            s.destination_station_id,
            s.first_train_time,
            s.last_train_time,
            s.frequency_min,
            s.operates_on,
            s.origin_stop_order,
            s.destination_stop_order,
            s.origin_time_min,
            s.destination_time_min,
            stop_lists.stops_in_order,
            stop_lists.passed_through_stations,
            origin_station.name,
            destination_station.name,
            seat_counts.total_seats
        ORDER BY s.line, s.first_train_time, s.schedule_id;
    """
    params = (
        origin_id,
        destination_id,
        travel_date,
        travel_date,
        origin_id,
        destination_id,
        origin_id,
        destination_id,
        travel_date,
        travel_date,
    )
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        fare_class:      "standard" or "first"
        stops_travelled: number of stops between origin and destination (inclusive)

    Returns:
        dict with fare_class, base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            fare_class,
            base_fare_usd,
            per_stop_rate_usd,
            %s::INTEGER AS stops_travelled,
            ROUND(base_fare_usd + (per_stop_rate_usd * %s::INTEGER), 2)
                AS total_fare_usd
        FROM national_rail_fares
        WHERE schedule_id = %s
          AND fare_class = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (stops_travelled, stops_travelled, schedule_id, fare_class))
            row = cur.fetchone()
            return dict(row) if row else None


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"

    Returns:
        List of matching metro schedules with stop count and travel time.
    """
    sql = """
        SELECT
            s.schedule_id,
            s.line,
            s.direction,
            s.origin_station_id AS schedule_origin_station_id,
            s.destination_station_id AS schedule_destination_station_id,
            stop_lists.stops_in_order,
            s.first_train_time,
            s.last_train_time,
            s.frequency_min,
            s.operates_on,
            s.base_fare_usd,
            s.per_stop_rate_usd,
            %s::VARCHAR AS requested_origin_id,
            %s::VARCHAR AS requested_destination_id,
            origin_station.name AS origin_name,
            destination_station.name AS destination_name,
            origin_stop.stop_order AS origin_stop_order,
            destination_stop.stop_order AS destination_stop_order,
            (destination_stop.stop_order - origin_stop.stop_order)::INTEGER
                AS stops_travelled,
            (
                destination_stop.travel_time_from_origin_min
                - origin_stop.travel_time_from_origin_min
            ) AS travel_time_min
        FROM metro_schedules s
        JOIN metro_schedule_stops origin_stop
            ON origin_stop.schedule_id = s.schedule_id
           AND origin_stop.station_id = %s
        JOIN metro_schedule_stops destination_stop
            ON destination_stop.schedule_id = s.schedule_id
           AND destination_stop.station_id = %s
        JOIN metro_stations origin_station
            ON origin_station.station_id = %s
        JOIN metro_stations destination_station
            ON destination_station.station_id = %s
        JOIN LATERAL (
            SELECT array_agg(station_id ORDER BY stop_order) AS stops_in_order
            FROM metro_schedule_stops stops
            WHERE stops.schedule_id = s.schedule_id
        ) stop_lists ON TRUE
        WHERE origin_stop.stop_order < destination_stop.stop_order
        ORDER BY s.line, s.first_train_time, s.schedule_id;
    """
    params = (
        origin_id,
        destination_id,
        origin_id,
        destination_id,
        origin_id,
        destination_id,
    )
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            base_fare_usd,
            per_stop_rate_usd,
            %s::INTEGER AS stops_travelled,
            ROUND(base_fare_usd + (per_stop_rate_usd * %s::INTEGER), 2)
                AS total_fare_usd
        FROM metro_schedules
        WHERE schedule_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (stops_travelled, stops_travelled, schedule_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id:  e.g. "NR_SCH01"
        travel_date:  e.g. "2025-06-01"
        fare_class:   "standard" or "first"

    Returns:
        List of dicts: {seat_id, coach, row, column}
    """
    sql = """
        SELECT
            seats.seat_id,
            seats.coach,
            seats.fare_class,
            seats.row_number AS row,
            seats.seat_column AS column
        FROM national_rail_seats seats
        LEFT JOIN national_rail_bookings b
            ON b.schedule_id = seats.schedule_id
            AND b.seat_id = seats.seat_id
            AND b.travel_date = %s::DATE
            AND b.fare_class = seats.fare_class
            AND b.status <> 'cancelled'
        WHERE seats.schedule_id = %s
          AND seats.fare_class = %s
          AND b.booking_id IS NULL
        ORDER BY seats.coach, seats.row_number, seats.seat_column, seats.seat_id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (travel_date, schedule_id, fare_class))
            return [dict(row) for row in cur.fetchall()]


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats: output of query_available_seats()
        count:           number of seats needed
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """
    Return a user's profile by email.

    Args:
        user_email: Registered user email address.

    Returns:
        User profile dict, or None if no active user is found.
    """
    sql = """
        SELECT
            user_id,
            full_name,
            first_name,
            surname,
            email,
            phone,
            date_of_birth,
            EXTRACT(YEAR FROM date_of_birth)::INTEGER AS year_of_birth,
            registered_at,
            is_active
        FROM registered_users
        WHERE email = %s
          AND is_active = TRUE;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Args:
        user_email: Registered user email address.

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    national_rail_sql = """
        SELECT
            b.booking_id,
            b.user_id,
            b.schedule_id,
            s.line,
            s.service_type,
            b.origin_station_id,
            origin_station.name AS origin_name,
            b.destination_station_id,
            destination_station.name AS destination_name,
            b.travel_date,
            b.departure_time,
            b.ticket_type,
            b.fare_class,
            b.coach,
            b.seat_id,
            b.stops_travelled,
            b.amount_usd,
            b.status,
            b.booked_at,
            b.travelled_at
        FROM national_rail_bookings b
        JOIN registered_users u ON u.user_id = b.user_id
        JOIN national_rail_schedules s ON s.schedule_id = b.schedule_id
        JOIN national_rail_stations origin_station
            ON origin_station.station_id = b.origin_station_id
        JOIN national_rail_stations destination_station
            ON destination_station.station_id = b.destination_station_id
        WHERE u.email = %s
        ORDER BY b.travel_date DESC, b.departure_time DESC, b.booking_id DESC;
    """
    metro_sql = """
        SELECT
            t.trip_id,
            t.user_id,
            t.schedule_id,
            s.line,
            t.origin_station_id,
            origin_station.name AS origin_name,
            t.destination_station_id,
            destination_station.name AS destination_name,
            t.travel_date,
            t.ticket_type,
            t.day_pass_ref,
            t.stops_travelled,
            t.amount_usd,
            t.status,
            t.purchased_at,
            t.travelled_at
        FROM metro_travels t
        JOIN registered_users u ON u.user_id = t.user_id
        JOIN metro_schedules s ON s.schedule_id = t.schedule_id
        JOIN metro_stations origin_station
            ON origin_station.station_id = t.origin_station_id
        JOIN metro_stations destination_station
            ON destination_station.station_id = t.destination_station_id
        WHERE u.email = %s
        ORDER BY t.travel_date DESC, t.travelled_at DESC, t.trip_id DESC;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(national_rail_sql, (user_email,))
            national_rail = [dict(row) for row in cur.fetchall()]
            cur.execute(metro_sql, (user_email,))
            metro = [dict(row) for row in cur.fetchall()]
            return {"national_rail": national_rail, "metro": metro}


def query_payment_info(booking_id: str) -> Optional[dict]:
    """
    Return payment record for a booking or metro trip.

    Args:
        booking_id: National rail booking ID (BK...) or metro trip ID (MT...).

    Returns:
        Payment dict, or None if no payment is found.
    """
    sql = """
        SELECT
            p.payment_id,
            COALESCE(p.booking_id, p.trip_id) AS booking_id,
            CASE
                WHEN rail.booking_id IS NOT NULL THEN 'national_rail'
                WHEN metro.trip_id IS NOT NULL THEN 'metro'
                ELSE 'unknown'
            END AS transaction_type,
            COALESCE(rail.user_id, metro.user_id) AS user_id,
            COALESCE(rail.status, metro.status) AS transaction_status,
            p.amount_usd,
            p.method,
            p.status,
            p.paid_at
        FROM payments p
        LEFT JOIN national_rail_bookings rail
            ON rail.booking_id = p.booking_id
        LEFT JOIN metro_travels metro
            ON metro.trip_id = p.trip_id
        WHERE p.booking_id = %s
           OR p.trip_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id, booking_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Args:
        user_id:                e.g. "RU01" — must match the logged-in user
        schedule_id:            e.g. "NR_SCH01"
        origin_station_id:      e.g. "NR01"
        destination_station_id: e.g. "NR05"
        travel_date:            e.g. "2025-06-01"
        fare_class:             "standard" or "first"
        seat_id:                e.g. "B05" (or "any" to auto-assign)
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, booking_dict)   on success
        (False, error_message) on failure
    """
    try:
        parsed_travel_date = datetime.strptime(travel_date, "%Y-%m-%d").date()
    except ValueError:
        return False, "Invalid travel_date format. Use YYYY-MM-DD."

    requested_seat_id = seat_id.strip()
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id
                FROM registered_users
                WHERE user_id = %s
                  AND is_active = TRUE;
                """,
                (user_id,),
            )
            if not cur.fetchone():
                conn.rollback()
                return False, "User not found or inactive."

            cur.execute(
                """
                SELECT
                    schedule_id,
                    first_train_time
                FROM national_rail_schedules
                WHERE schedule_id = %s;
                """,
                (schedule_id,),
            )
            schedule = cur.fetchone()
            if not schedule:
                conn.rollback()
                return False, "Schedule not found."

            cur.execute(
                """
                SELECT
                    s.schedule_id,
                    s.first_train_time,
                    origin_stop.stop_order AS origin_stop_order,
                    destination_stop.stop_order AS destination_stop_order,
                    (destination_stop.stop_order - origin_stop.stop_order)::INTEGER
                        AS stops_travelled
                FROM national_rail_schedules s
                JOIN national_rail_schedule_stops origin_stop
                    ON origin_stop.schedule_id = s.schedule_id
                   AND origin_stop.station_id = %s
                JOIN national_rail_schedule_stops destination_stop
                    ON destination_stop.schedule_id = s.schedule_id
                   AND destination_stop.station_id = %s
                WHERE s.schedule_id = %s
                  AND origin_stop.stop_order < destination_stop.stop_order;
                """,
                (origin_station_id, destination_station_id, schedule_id),
            )
            route = cur.fetchone()
            if not route:
                conn.rollback()
                return False, "Invalid route: origin and destination must be on the schedule in order."

            cur.execute(
                """
                SELECT
                    fare_class,
                    base_fare_usd,
                    per_stop_rate_usd
                FROM national_rail_fares
                WHERE schedule_id = %s
                  AND fare_class = %s;
                """,
                (schedule_id, fare_class),
            )
            fare = cur.fetchone()
            if not fare:
                conn.rollback()
                return False, "Fare class not found for this schedule."

            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s));",
                (f"{schedule_id}:{parsed_travel_date.isoformat()}",),
            )

            if requested_seat_id.lower() == "any":
                cur.execute(
                    """
                    SELECT
                        seats.seat_id,
                        seats.coach,
                        seats.fare_class
                    FROM national_rail_seats seats
                    WHERE seats.schedule_id = %s
                      AND seats.fare_class = %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM national_rail_bookings b
                          WHERE b.schedule_id = seats.schedule_id
                            AND b.travel_date = %s::DATE
                            AND b.seat_id = seats.seat_id
                            AND b.status <> 'cancelled'
                      )
                    ORDER BY seats.coach, seats.row_number, seats.seat_column, seats.seat_id
                    LIMIT 1
                    FOR UPDATE;
                    """,
                    (schedule_id, fare_class, parsed_travel_date),
                )
                seat = cur.fetchone()
                if not seat:
                    conn.rollback()
                    return False, "No available seats."
            else:
                cur.execute(
                    """
                    SELECT
                        seat_id,
                        coach,
                        fare_class
                    FROM national_rail_seats
                    WHERE schedule_id = %s
                      AND seat_id = %s
                    FOR UPDATE;
                    """,
                    (schedule_id, requested_seat_id),
                )
                seat = cur.fetchone()
                if not seat:
                    conn.rollback()
                    return False, "Seat does not exist for this schedule."
                if seat["fare_class"] != fare_class:
                    conn.rollback()
                    return False, "Seat fare_class does not match requested fare_class."

            cur.execute(
                """
                SELECT booking_id
                FROM national_rail_bookings
                WHERE schedule_id = %s
                  AND travel_date = %s::DATE
                  AND seat_id = %s
                  AND status <> 'cancelled'
                LIMIT 1;
                """,
                (schedule_id, parsed_travel_date, seat["seat_id"]),
            )
            if cur.fetchone():
                conn.rollback()
                return False, "Seat is already booked."

            booking_id = None
            for _ in range(20):
                candidate = _gen_booking_id()
                cur.execute(
                    """
                    SELECT booking_id
                    FROM national_rail_bookings
                    WHERE booking_id = %s;
                    """,
                    (candidate,),
                )
                if not cur.fetchone():
                    booking_id = candidate
                    break
            if booking_id is None:
                conn.rollback()
                return False, "Could not generate a unique booking_id."

            amount_usd = (
                fare["base_fare_usd"]
                + fare["per_stop_rate_usd"] * route["stops_travelled"]
            )
            booked_at = datetime.now(timezone.utc)

            cur.execute(
                """
                INSERT INTO national_rail_bookings (
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    departure_time,
                    ticket_type,
                    fare_class,
                    coach,
                    seat_id,
                    stops_travelled,
                    amount_usd,
                    status,
                    booked_at,
                    travelled_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 'confirmed', %s, NULL
                )
                RETURNING
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    departure_time,
                    ticket_type,
                    fare_class,
                    coach,
                    seat_id,
                    stops_travelled,
                    amount_usd,
                    status,
                    booked_at,
                    travelled_at;
                """,
                (
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    parsed_travel_date,
                    schedule["first_train_time"],
                    ticket_type,
                    fare_class,
                    seat["coach"],
                    seat["seat_id"],
                    route["stops_travelled"],
                    amount_usd,
                    booked_at,
                ),
            )
            booking = dict(cur.fetchone())

            payment_id = None
            for _ in range(20):
                candidate = _gen_payment_id()
                cur.execute(
                    """
                    SELECT payment_id
                    FROM payments
                    WHERE payment_id = %s;
                    """,
                    (candidate,),
                )
                if not cur.fetchone():
                    payment_id = candidate
                    break
            if payment_id is None:
                conn.rollback()
                return False, "Could not generate a unique payment_id."

            cur.execute(
                """
                INSERT INTO payments (
                    payment_id,
                    booking_id,
                    trip_id,
                    amount_usd,
                    method,
                    status,
                    paid_at
                )
                VALUES (%s, %s, NULL, %s, 'credit_card', 'paid', %s);
                """,
                (payment_id, booking_id, amount_usd, booked_at),
            )
            booking["payment_id"] = payment_id
        conn.commit()
        return True, booking
    except psycopg2.Error as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Marks a confirmed booking as cancelled. The refund amount returned by this
    stage is the original booking amount.

    Args:
        booking_id: e.g. "BK001"
        user_id:    must match the booking's user_id

    Returns:
        (True, result_dict)  with booking_id, status, and refund_amount_usd
        (False, error_msg)
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    booking_id,
                    user_id,
                    amount_usd,
                    status,
                    travel_date,
                    departure_time,
                    s.service_type
                FROM national_rail_bookings b
                JOIN national_rail_schedules s ON s.schedule_id = b.schedule_id
                WHERE booking_id = %s
                FOR UPDATE;
                """,
                (booking_id,),
            )
            booking = cur.fetchone()
            if not booking:
                conn.rollback()
                return False, "Booking not found."
            if booking["user_id"] != user_id:
                conn.rollback()
                return False, "Booking does not belong to this user."
            if booking["status"] == "cancelled":
                conn.rollback()
                return False, "Booking is already cancelled."
            if booking["status"] == "completed":
                conn.rollback()
                return False, "Completed booking cannot be cancelled."
            if booking["status"] != "confirmed":
                conn.rollback()
                return False, "Only confirmed bookings can be cancelled."

            departure_time = booking["departure_time"]
            if isinstance(departure_time, str):
                departure_time = time.fromisoformat(departure_time)
            departure_at = datetime.combine(
                booking["travel_date"],
                departure_time,
                tzinfo=timezone.utc,
            )
            hours_before = (departure_at - datetime.now(timezone.utc)).total_seconds() / 3600

            if booking["service_type"] == "express":
                if hours_before >= 48:
                    refund_percent, admin_fee = 100, Decimal("1.00")
                elif hours_before >= 24:
                    refund_percent, admin_fee = 50, Decimal("1.00")
                else:
                    refund_percent, admin_fee = 0, Decimal("0.00")
            else:
                if hours_before >= 48:
                    refund_percent, admin_fee = 100, Decimal("0.00")
                elif hours_before >= 24:
                    refund_percent, admin_fee = 75, Decimal("0.50")
                elif hours_before >= 2:
                    refund_percent, admin_fee = 50, Decimal("0.50")
                else:
                    refund_percent, admin_fee = 0, Decimal("0.00")

            refund_amount = max(
                booking["amount_usd"] * Decimal(refund_percent) / Decimal("100") - admin_fee,
                Decimal("0.00"),
            )

            cur.execute(
                """
                UPDATE national_rail_bookings
                SET status = 'cancelled'
                WHERE booking_id = %s
                RETURNING
                    booking_id,
                    status;
                """,
                (booking_id,),
            )
            result = dict(cur.fetchone())
            result["refund_amount_usd"] = round(refund_amount, 2)
            result["refund_percent"] = refund_percent
            result["admin_fee_usd"] = admin_fee

            cur.execute(
                """
                UPDATE payments
                SET status = CASE WHEN %s > 0 THEN 'refunded' ELSE status END
                WHERE booking_id = %s;
                """,
                (refund_amount, booking_id),
            )
        conn.commit()
        return True, result
    except psycopg2.Error as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user.

    Args:
        email: Registered email address.
        first_name: User's first name.
        surname: User's surname.
        year_of_birth: Four-digit birth year.
        password: Plain text password to hash before storing.
        secret_question: Password recovery question.
        secret_answer: Password recovery answer.

    Returns:
        (True, user_id) on success, or (False, error_message) on failure.
    """
    normalized_email = email.strip().lower()
    clean_first_name = first_name.strip()
    clean_surname = surname.strip()
    full_name = f"{clean_first_name} {clean_surname}".strip()
    try:
        birth_year = int(year_of_birth)
    except (TypeError, ValueError):
        return False, "Invalid year of birth."
    date_of_birth = f"{birth_year:04d}-01-01"
    now = datetime.now(timezone.utc)
    password_hash = _PASSWORD_HASHER.hash(password)

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id
                FROM registered_users
                WHERE email = %s;
                """,
                (normalized_email,),
            )
            if cur.fetchone():
                conn.rollback()
                return False, "Email already registered."

            cur.execute(
                """
                SELECT user_id
                FROM registered_users
                WHERE user_id LIKE 'RU%%'
                ORDER BY CAST(SUBSTRING(user_id FROM 3) AS INTEGER) DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()
            next_number = int(row["user_id"][2:]) + 1 if row else 1
            user_id = f"RU{next_number:02d}"

            cur.execute(
                """
                INSERT INTO registered_users (
                    user_id,
                    full_name,
                    first_name,
                    surname,
                    email,
                    phone,
                    date_of_birth,
                    secret_question,
                    secret_answer,
                    registered_at,
                    is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE);
                """,
                (
                    user_id,
                    full_name,
                    clean_first_name,
                    clean_surname,
                    normalized_email,
                    None,
                    date_of_birth,
                    secret_question.strip(),
                    secret_answer.strip(),
                    now,
                ),
            )
            cur.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id,
                    password_hash,
                    password_updated_at
                )
                VALUES (%s, %s, %s);
                """,
                (user_id, password_hash, now),
            )
        conn.commit()
        return True, user_id
    except (psycopg2.Error, ValueError) as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials.

    Args:
        email: Registered user email address.
        password: Plain text password to verify against the Argon2id hash.

    Returns:
        User profile dict on success, or None on failure.
    """
    sql = """
        SELECT
            u.user_id,
            u.full_name,
            u.first_name,
            u.surname,
            u.email,
            u.phone,
            u.date_of_birth,
            u.registered_at,
            u.is_active,
            c.password_hash
        FROM registered_users u
        JOIN user_password_credentials c ON c.user_id = u.user_id
        WHERE u.email = %s
          AND u.is_active = TRUE;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email.strip().lower(),))
            row = cur.fetchone()
            if not row:
                return None

            try:
                _PASSWORD_HASHER.verify(row["password_hash"], password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return None

            user = dict(row)
            user.pop("password_hash", None)
            return user


def get_user_secret_question(email: str) -> Optional[str]:
    """
    Return the secret question for a registered email.

    Args:
        email: Registered user email address.

    Returns:
        Secret question string, or None if no active user is found.
    """
    sql = """
        SELECT secret_question
        FROM registered_users
        WHERE email = %s
          AND is_active = TRUE;
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email.strip().lower(),))
            row = cur.fetchone()
            return row[0] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """
    Return True if the provided answer matches the stored secret answer.

    Args:
        email: Registered user email address.
        answer: Candidate password recovery answer.

    Returns:
        True for a case-insensitive trimmed match, otherwise False.
    """
    sql = """
        SELECT secret_answer
        FROM registered_users
        WHERE email = %s
          AND is_active = TRUE;
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email.strip().lower(),))
            row = cur.fetchone()
            if not row:
                return False
            return row[0].strip().lower() == answer.strip().lower()


def update_password(email: str, new_password: str) -> bool:
    """
    Update the password for an active user.

    Args:
        email: Registered user email address.
        new_password: Plain text password to hash before storing.

    Returns:
        True if the password credential row was updated, otherwise False.
    """
    password_hash = _PASSWORD_HASHER.hash(new_password)
    sql = """
        UPDATE user_password_credentials c
        SET
            password_hash = %s,
            password_updated_at = %s
        FROM registered_users u
        WHERE u.user_id = c.user_id
          AND u.email = %s
          AND u.is_active = TRUE;
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (password_hash, datetime.now(timezone.utc), email.strip().lower()),
            )
            return cur.rowcount == 1


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
