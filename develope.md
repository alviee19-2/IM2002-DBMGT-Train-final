# TransitFlow Development Plan

這份文件用來固定團隊開發流程，避免大家在 schema、seed script、query function 上各做各的。

目前階段：先完成 relational schema 設計，再進行 seed script、query function、graph database 的分工。

---

## 1. Development Rule

### Schema First

在任何人實作 `databases/relational/queries.py` 之前，團隊必須先共同決定並確認：

- PostgreSQL table names
- PostgreSQL column names and data types
- primary keys and foreign keys
- 哪些欄位用 JSONB 儲存
- query functions 預期回傳哪些欄位

原因：query functions 會直接依賴 schema。如果 schema 還沒定，後面每個人的 SQL 都可能用到不同 table 或 column name。

### Shared Contract

確認後的 schema 決策必須同步更新到：

- `develope.md`
- `AI_SESSION_CONTEXT.md`
- `databases/relational/schema.sql`

`AI_SESSION_CONTEXT.md` 是每次開 AI session 時要貼給 AI 的上下文，所以它必須跟實際 schema 保持一致。

---

## 2. Current Project Status

目前 codebase 還是 starter 狀態：

- `databases/relational/schema.sql`：尚未建立 relational tables，只有 pgvector policy table。
- `skeleton/seed_postgres.py`：所有 seed function 還是 TODO。
- `databases/relational/queries.py`：主要 relational query functions 尚未實作。
- `skeleton/seed_neo4j.py`：graph seed 尚未實作。
- `databases/graph/queries.py`：graph query functions 尚未實作。

因此現在最重要的工作不是先寫 Python，而是先把 relational schema 定案。

---

## 3. Data Files To Support

Relational database 需要支援以下 mock data：

- `metro_stations.json`
- `national_rail_stations.json`
- `metro_schedules.json`
- `national_rail_schedules.json`
- `national_rail_seat_layouts.json`
- `registered_users.json`
- `bookings.json`
- `metro_travel_history.json`
- `payments.json`
- `feedback.json`

以下 policy files 由 pgvector/RAG 使用，已經有現成流程，暫時不放進 relational schema：

- `ticket_types.json`
- `refund_policy.json`
- `booking_rules.json`
- `travel_policies.json`

---

## 4. Proposed Relational Schema

這是目前建議的 schema 草案。目標是讓 query functions 容易寫、seed script 容易實作，同時保留 PostgreSQL relational design 的重點。

### 4.1 Stations

#### `metro_stations`

Stores city metro station metadata.

Suggested columns:

```sql
station_id VARCHAR(10) PRIMARY KEY,
name TEXT NOT NULL,
lines TEXT[] NOT NULL,
is_interchange_metro BOOLEAN NOT NULL DEFAULT FALSE,
interchange_metro_lines TEXT[] NOT NULL DEFAULT '{}',
is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
interchange_national_rail_station_id VARCHAR(10)
```

Decision:

- `lines` and `interchange_metro_lines` use `TEXT[]`.
- Adjacent station data is not stored here because route-finding belongs to Neo4j.
- `interchange_national_rail_station_id` points to national rail station ID, but we may avoid strict FK at first because metro and rail station tables reference each other.

#### `national_rail_stations`

Stores national rail station metadata.

Suggested columns:

```sql
station_id VARCHAR(10) PRIMARY KEY,
name TEXT NOT NULL,
lines TEXT[] NOT NULL,
is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
interchange_national_rail_lines TEXT[] NOT NULL DEFAULT '{}',
is_interchange_metro BOOLEAN NOT NULL DEFAULT FALSE,
interchange_metro_station_id VARCHAR(10)
```

Decision:

- Same station design pattern as metro.
- Adjacent station data goes to Neo4j, not PostgreSQL.

---

### 4.2 Schedules

#### `metro_schedules`

Stores metro timetable and fare information.

Suggested columns:

```sql
schedule_id VARCHAR(20) PRIMARY KEY,
line VARCHAR(10) NOT NULL,
direction VARCHAR(20) NOT NULL,
origin_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
stops_in_order JSONB NOT NULL,
first_train_time TIME NOT NULL,
last_train_time TIME NOT NULL,
travel_time_from_origin_min JSONB NOT NULL,
base_fare_usd NUMERIC(8,2) NOT NULL,
per_stop_rate_usd NUMERIC(8,2) NOT NULL,
frequency_min INTEGER NOT NULL,
operates_on TEXT[] NOT NULL
```

Decision:

- `stops_in_order` stays as `JSONB` because query functions can use `jsonb_array_elements_text(... WITH ORDINALITY)` to check station order.
- `travel_time_from_origin_min` stays as `JSONB` because it is a station-id-to-minutes mapping.
- Fare is simple for metro, so it stays directly on the schedule.

#### `national_rail_schedules`

Stores national rail timetable, service type, and route structure.

Suggested columns:

```sql
schedule_id VARCHAR(20) PRIMARY KEY,
line VARCHAR(10) NOT NULL,
service_type VARCHAR(20) NOT NULL,
direction VARCHAR(20) NOT NULL,
origin_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
stops_in_order JSONB NOT NULL,
passed_through_stations JSONB NOT NULL DEFAULT '[]',
first_train_time TIME NOT NULL,
last_train_time TIME NOT NULL,
travel_time_from_origin_min JSONB NOT NULL,
frequency_min INTEGER NOT NULL,
operates_on TEXT[] NOT NULL
```

Decision:

- Keep route order and travel time mapping as `JSONB`.
- Express services may have `passed_through_stations`; normal services can store `[]`.
- Fare classes are normalized into a separate table.

#### `national_rail_fares`

Stores fare rules per national rail schedule and fare class.

Suggested columns:

```sql
schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id),
fare_class VARCHAR(20) NOT NULL,
base_fare_usd NUMERIC(8,2) NOT NULL,
per_stop_rate_usd NUMERIC(8,2) NOT NULL,
PRIMARY KEY (schedule_id, fare_class)
```

Decision:

- Normalize `fare_classes` from JSON into rows.
- This makes `query_national_rail_fare(schedule_id, fare_class, stops_travelled)` straightforward.

---

### 4.3 Seats

#### `national_rail_seat_layouts`

Stores seat layout header per schedule.

Suggested columns:

```sql
layout_id VARCHAR(20) PRIMARY KEY,
schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id)
```

#### `national_rail_seats`

Stores individual seats for each schedule layout.

Suggested columns:

```sql
layout_id VARCHAR(20) NOT NULL REFERENCES national_rail_seat_layouts(layout_id),
schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id),
coach VARCHAR(5) NOT NULL,
fare_class VARCHAR(20) NOT NULL,
seat_id VARCHAR(10) NOT NULL,
row_number INTEGER NOT NULL,
seat_column VARCHAR(5) NOT NULL,
PRIMARY KEY (schedule_id, seat_id)
```

Decision:

- Flatten coach/seats JSON into individual seat rows.
- Use `row_number` instead of `row` because `row` can be confusing as a SQL term.
- Use `seat_column` instead of `column` because `column` is a SQL concept.

---

### 4.4 Users

#### `registered_users`

Stores account and authentication data.

Suggested columns:

```sql
user_id VARCHAR(20) PRIMARY KEY,
full_name TEXT NOT NULL,
first_name TEXT NOT NULL,
surname TEXT NOT NULL,
email TEXT NOT NULL UNIQUE,
password TEXT NOT NULL,
phone TEXT,
date_of_birth DATE,
secret_question TEXT NOT NULL,
secret_answer TEXT NOT NULL,
registered_at TIMESTAMPTZ NOT NULL,
is_active BOOLEAN NOT NULL DEFAULT TRUE
```

Decision:

- The source JSON only has `full_name`, but UI expects `first_name` and `surname`, so seed script should split `full_name`.
- Password remains plain text because README says this is intentional for teaching.

---

### 4.5 Transactions

#### `national_rail_bookings`

Stores advance national rail bookings.

Suggested columns:

```sql
booking_id VARCHAR(20) PRIMARY KEY,
user_id VARCHAR(20) NOT NULL REFERENCES registered_users(user_id),
schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id),
origin_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
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
```

Decision:

- Keep booking details denormalized enough for easy history queries.
- `seat_id` can be nullable for flexibility, but mock data has seats.

#### `metro_travels`

Stores metro tap-in / trip history.

Suggested columns:

```sql
trip_id VARCHAR(20) PRIMARY KEY,
user_id VARCHAR(20) NOT NULL REFERENCES registered_users(user_id),
schedule_id VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id),
origin_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
travel_date DATE NOT NULL,
ticket_type VARCHAR(20) NOT NULL,
day_pass_ref VARCHAR(20),
stops_travelled INTEGER,
amount_usd NUMERIC(8,2) NOT NULL,
status VARCHAR(20) NOT NULL,
purchased_at TIMESTAMPTZ,
travelled_at TIMESTAMPTZ
```

Decision:

- Metro trips are separate from national rail bookings because business rules differ.
- `day_pass_ref`, `stops_travelled`, and `purchased_at` can be nullable.

#### `payments`

Stores payment record for either a national rail booking or metro trip.

Suggested columns:

```sql
payment_id VARCHAR(20) PRIMARY KEY,
booking_id VARCHAR(20) NOT NULL,
amount_usd NUMERIC(8,2) NOT NULL,
method VARCHAR(30) NOT NULL,
status VARCHAR(20) NOT NULL,
paid_at TIMESTAMPTZ NOT NULL
```

Decision:

- Keep `booking_id` as a generic transaction reference because source data uses the same field for both `BK...` and `MT...`.
- Do not add FK here because it can point to either `national_rail_bookings.booking_id` or `metro_travels.trip_id`.

#### `feedback`

Stores passenger feedback.

Suggested columns:

```sql
feedback_id VARCHAR(20) PRIMARY KEY,
booking_id VARCHAR(20) NOT NULL,
user_id VARCHAR(20) NOT NULL REFERENCES registered_users(user_id),
rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
comment TEXT,
submitted_at TIMESTAMPTZ NOT NULL
```

Decision:

- Same as `payments`, `booking_id` is a generic reference to either national rail or metro transaction.

---

## 5. Query Functions Supported By This Schema

This schema is designed to support:

- `query_national_rail_availability`
- `query_national_rail_fare`
- `query_metro_schedules`
- `query_metro_fare`
- `query_available_seats`
- `query_user_profile`
- `query_user_bookings`
- `query_payment_info`
- `execute_booking`
- `execute_cancellation`
- `register_user`
- `login_user`
- `get_user_secret_question`
- `verify_secret_answer`
- `update_password`

Important implementation decisions:

- Schedule order checks should use `jsonb_array_elements_text(... WITH ORDINALITY)`.
- Available seats should query `national_rail_seats` and exclude confirmed bookings for the same schedule/date/fare class.
- User booking history should return:
  - `national_rail`: rows from `national_rail_bookings`
  - `metro`: rows from `metro_travels`
- `query_payment_info(booking_id)` should work for both `BK...` and `MT...` IDs.

---

## 6. Recommended Team Division

After schema is approved:

### Person A: Relational Schema + Seed

Files:

- `databases/relational/schema.sql`
- `skeleton/seed_postgres.py`

Tasks:

- Convert this schema plan into SQL.
- Implement all seed functions.
- Verify row counts after seeding.

### Person B: Relational Query Functions

Files:

- `databases/relational/queries.py`

Tasks:

- Implement read-only queries first.
- Then implement auth functions.
- Finally implement booking/cancellation writes.

### Person C: Graph Schema + Graph Queries + Integration

Files:

- `skeleton/seed_neo4j.py`
- `databases/graph/queries.py`

Tasks:

- Decide Neo4j labels and relationships.
- Seed metro and national rail network links.
- Implement shortest route, alternative route, interchange path, delay ripple.
- Run integration tests through Gradio debug panel.

---

## 7. Immediate Next Steps

1. Team reviews this relational schema proposal.
2. Confirm or revise table/column names.
3. Copy final decisions into `AI_SESSION_CONTEXT.md`.
4. Implement `databases/relational/schema.sql`.
5. Reset Docker volumes and verify PostgreSQL creates tables.
6. Implement `skeleton/seed_postgres.py`.
7. Implement relational query functions.
8. Move to Neo4j graph schema and graph query implementation.

---

## 8. Open Questions For Team Review

- Should station interchange fields use strict foreign keys, or keep them as nullable ID references without FK?
- Should `payments.booking_id` be renamed to `transaction_id` in our schema even though the source JSON calls it `booking_id`?
- Should we create extra normalized station-line tables, or keep `TEXT[]` arrays for simplicity?
- Should `stops_in_order` be `JSONB` or a normalized schedule stops table?

Current recommendation:

- Use nullable ID references for interchange fields.
- Keep `payments.booking_id` to match source JSON and query function naming.
- Use `TEXT[]` for station lines.
- Use `JSONB` for schedule stop order because it is simple and fits the assignment scope.
