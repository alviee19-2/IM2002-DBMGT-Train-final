-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================

CREATE TABLE IF NOT EXISTS metro_stations (
    -- Natural station codes are stable in the mock operator data and make
    -- joins/readouts easier than surrogate IDs for this teaching dataset.
    station_id VARCHAR(10) PRIMARY KEY,
    name TEXT NOT NULL,
    lines TEXT[] NOT NULL,
    is_interchange_metro BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_metro_lines TEXT[] NOT NULL DEFAULT '{}',
    is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_national_rail_station_id VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS national_rail_stations (
    -- Natural station codes are stable in the mock operator data and make
    -- joins/readouts easier than surrogate IDs for this teaching dataset.
    station_id VARCHAR(10) PRIMARY KEY,
    name TEXT NOT NULL,
    lines TEXT[] NOT NULL,
    is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_national_rail_lines TEXT[] NOT NULL DEFAULT '{}',
    is_interchange_metro BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_metro_station_id VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS metro_schedules (
    -- Schedule IDs come from the timetable feed; keeping them as PKs avoids an
    -- extra lookup layer in booking and route queries.
    schedule_id VARCHAR(20) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    origin_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    first_train_time TIME NOT NULL,
    last_train_time TIME NOT NULL,
    base_fare_usd NUMERIC(8,2) NOT NULL,
    per_stop_rate_usd NUMERIC(8,2) NOT NULL,
    frequency_min INTEGER NOT NULL,
    operates_on TEXT[] NOT NULL
);

CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    schedule_id VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    stop_order INTEGER NOT NULL,
    travel_time_from_origin_min INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, station_id),
    UNIQUE (schedule_id, stop_order)
);

CREATE TABLE IF NOT EXISTS national_rail_schedules (
    -- Schedule IDs come from the timetable feed; keeping them as PKs avoids an
    -- extra lookup layer in booking and route queries.
    schedule_id VARCHAR(20) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    service_type VARCHAR(20) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    origin_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    first_train_time TIME NOT NULL,
    last_train_time TIME NOT NULL,
    frequency_min INTEGER NOT NULL,
    operates_on TEXT[] NOT NULL
);

CREATE TABLE IF NOT EXISTS national_rail_schedule_stops (
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    stop_order INTEGER NOT NULL,
    travel_time_from_origin_min INTEGER NOT NULL,
    is_passed_through BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (schedule_id, station_id),
    UNIQUE (schedule_id, stop_order)
);

CREATE TABLE IF NOT EXISTS national_rail_fares (
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    fare_class VARCHAR(20) NOT NULL,
    base_fare_usd NUMERIC(8,2) NOT NULL,
    per_stop_rate_usd NUMERIC(8,2) NOT NULL,
    PRIMARY KEY (schedule_id, fare_class)
);

CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    layout_id VARCHAR(20) PRIMARY KEY,
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS national_rail_seats (
    layout_id VARCHAR(20) NOT NULL REFERENCES national_rail_seat_layouts(layout_id) ON DELETE CASCADE,
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    coach VARCHAR(5) NOT NULL,
    fare_class VARCHAR(20) NOT NULL,
    seat_id VARCHAR(10) NOT NULL,
    row_number INTEGER NOT NULL,
    seat_column VARCHAR(5) NOT NULL,
    PRIMARY KEY (schedule_id, seat_id)
);

CREATE TABLE IF NOT EXISTS registered_users (
    -- User IDs are visible in mock data and live-test prompts, so we keep the
    -- provided RUxx code as the primary key.
    user_id VARCHAR(20) PRIMARY KEY,
    full_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    surname TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    date_of_birth DATE,
    secret_question TEXT NOT NULL,
    secret_answer TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS user_password_credentials (
    user_id VARCHAR(20) PRIMARY KEY REFERENCES registered_users(user_id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    password_updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS national_rail_bookings (
    booking_id VARCHAR(20) PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL REFERENCES registered_users(user_id) ON DELETE RESTRICT,
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    travel_date DATE NOT NULL,
    departure_time TIME NOT NULL,
    ticket_type VARCHAR(20) NOT NULL,
    fare_class VARCHAR(20) NOT NULL,
    coach VARCHAR(5),
    seat_id VARCHAR(10),
    stops_travelled INTEGER NOT NULL,
    amount_usd NUMERIC(8,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    booked_at TIMESTAMPTZ NOT NULL,
    travelled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS metro_travels (
    trip_id VARCHAR(20) PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL REFERENCES registered_users(user_id) ON DELETE RESTRICT,
    schedule_id VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(20) NOT NULL,
    day_pass_ref VARCHAR(20),
    stops_travelled INTEGER,
    amount_usd NUMERIC(8,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    purchased_at TIMESTAMPTZ,
    travelled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id VARCHAR(20) PRIMARY KEY,
    booking_id VARCHAR(20) REFERENCES national_rail_bookings(booking_id) ON DELETE RESTRICT,
    trip_id VARCHAR(20) REFERENCES metro_travels(trip_id) ON DELETE RESTRICT,
    amount_usd NUMERIC(8,2) NOT NULL,
    method VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (booking_id IS NOT NULL AND trip_id IS NULL)
        OR (booking_id IS NULL AND trip_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id VARCHAR(20) PRIMARY KEY,
    booking_id VARCHAR(20) REFERENCES national_rail_bookings(booking_id) ON DELETE RESTRICT,
    trip_id VARCHAR(20) REFERENCES metro_travels(trip_id) ON DELETE RESTRICT,
    user_id VARCHAR(20) NOT NULL REFERENCES registered_users(user_id) ON DELETE RESTRICT,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    submitted_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (booking_id IS NOT NULL AND trip_id IS NULL)
        OR (booking_id IS NULL AND trip_id IS NOT NULL)
    )
);



-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- Current project setting is Gemini. If you switch to Ollama, change to vector(768) and reset the database.
    embedding   vector(3072),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- HNSW indexes in pgvector cannot be created on 3072-dimensional vector columns.
-- Gemini uses 3072 dimensions, so policy search runs as an exact cosine scan.
