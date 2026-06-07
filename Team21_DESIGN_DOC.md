# TransitFlow Database Design Document

Team 21

---

## Section 1 — Entity-Relationship Diagram

### ER Diagram

![TransitFlow ER Diagram](<Order and Payment-2026-06-06-113810.png>)

### 實體設計說明

本系統的 relational database model 是根據最終開發版本中的 `databases/relational/schema.sql` 設計。ER diagram 主要呈現 TransitFlow 中 metro、national rail、使用者、訂票、付款與回饋之間的資料關係。圖中每個 entity 都標示 primary key、重要 foreign key，以及能代表該 entity 的主要欄位。

| Entity | Primary Key | 重要 Foreign Keys | 代表性欄位 |
|--------|-------------|------------------|------------|
| `metro_stations` | `station_id` | `interchange_national_rail_station_id` | `name`, `lines`, `is_interchange_metro`, `is_interchange_national_rail` |
| `national_rail_stations` | `station_id` | `interchange_metro_station_id` | `name`, `lines`, `is_interchange_national_rail`, `is_interchange_metro` |
| `metro_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id` | `line`, `direction`, `first_train_time`, `last_train_time`, `frequency_min` |
| `metro_schedule_stops` | (`schedule_id`, `station_id`) | `schedule_id`, `station_id` | `stop_order`, `travel_time_from_origin_min` |
| `national_rail_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id` | `line`, `service_type`, `direction`, `frequency_min` |
| `national_rail_schedule_stops` | (`schedule_id`, `station_id`) | `schedule_id`, `station_id` | `stop_order`, `travel_time_from_origin_min`, `is_passed_through` |
| `national_rail_fares` | (`schedule_id`, `fare_class`) | `schedule_id` | `base_fare_usd`, `per_stop_rate_usd` |
| `national_rail_seat_layouts` | `layout_id` | `schedule_id` | 座位配置所屬的 rail schedule |
| `national_rail_seats` | (`schedule_id`, `seat_id`) | `layout_id`, `schedule_id` | `coach`, `fare_class`, `row_number`, `seat_column` |
| `registered_users` | `user_id` | 無 | `full_name`, `email`, `phone`, `date_of_birth`, `is_active` |
| `user_password_credentials` | `user_id` | `user_id` | `password_hash`, `password_updated_at` |
| `national_rail_bookings` | `booking_id` | `user_id`, `schedule_id`, `origin_station_id`, `destination_station_id` | `travel_date`, `departure_time`, `fare_class`, `seat_id`, `amount_usd`, `status` |
| `metro_travels` | `trip_id` | `user_id`, `schedule_id`, `origin_station_id`, `destination_station_id` | `travel_date`, `ticket_type`, `amount_usd`, `status` |
| `payments` | `payment_id` | `booking_id` 或 `trip_id` | `amount_usd`, `method`, `status`, `paid_at` |
| `feedback` | `feedback_id` | `booking_id` 或 `trip_id`, `user_id` | `rating`, `comment`, `submitted_at` |

`policy_documents` 雖然也存在於 PostgreSQL 中，但它屬於 vector / RAG 設計，不是核心 ER model 的主要交易資料。它負責儲存 policy documents 的 embedding，會在 Vector / RAG Design section 中另外說明。

### 主要關係與 Cardinality

ER diagram 中的主要 relationship 與 cardinality 如下。這些 cardinality 也應該直接標示在圖中的 relationship line 上。

| Relationship | Cardinality | 說明 |
|--------------|-------------|------|
| `metro_stations` 到 `metro_schedules` 的 origin / destination | 1:N | 一個 metro station 可以作為多個 metro schedules 的起點或終點；每個 schedule 只有一個起點與一個終點。 |
| `national_rail_stations` 到 `national_rail_schedules` 的 origin / destination | 1:N | 一個 national rail station 可以出現在多個 rail schedules 中；每個 rail schedule 只有一個起點與一個終點。 |
| `metro_schedules` 與 `metro_stations` 透過 `metro_schedule_stops` 連接 | M:N | 一個 metro schedule 會經過多個 station，而同一個 station 也會出現在多個 schedules 中。junction table 負責記錄站序與從起點出發的 travel time。 |
| `national_rail_schedules` 與 `national_rail_stations` 透過 `national_rail_schedule_stops` 連接 | M:N | 一個 national rail schedule 會經過多個 rail station，而同一個 station 也可能被多個 schedules 使用。此表也記錄該站是否只是 pass-through。 |
| `national_rail_schedules` 到 `national_rail_fares` | 1:N | 一個 rail schedule 可以有多個 fare class，例如 `standard` 和 `first`。用 (`schedule_id`, `fare_class`) 作為 composite key 可避免同一 schedule 出現重複 fare class。 |
| `national_rail_schedules` 到 `national_rail_seat_layouts` | 1:N | 一個 schedule 可以對應一個或多個 seat layout record；每個 layout 屬於一個 schedule。 |
| `national_rail_seat_layouts` 到 `national_rail_seats` | 1:N | 一個 layout 包含多個個別座位；每個座位 row 都屬於某個 layout。 |
| `registered_users` 到 `user_password_credentials` | 1:1 | 每個使用者只有一筆 credentials record。密碼資料和 profile data 分開儲存。 |
| `registered_users` 到 `national_rail_bookings` | 1:N | 一個使用者可以建立多筆 national rail booking；每筆 booking 只屬於一個使用者。 |
| `registered_users` 到 `metro_travels` | 1:N | 一個使用者可以有多筆 metro travel history；每筆 metro trip 只屬於一個使用者。 |
| `national_rail_schedules` 到 `national_rail_bookings` | 1:N | 一個 rail schedule 可以被多次預訂；每筆 booking 對應一個 schedule。 |
| `metro_schedules` 到 `metro_travels` | 1:N | 一個 metro schedule 可以出現在多筆 metro travel records 中；每筆 trip 對應一個 schedule。 |
| `national_rail_bookings` 到 `payments` | 1:N，可選父交易 | 一筆 rail booking 可以有 payment record。payment 可以連到 rail booking 或 metro trip，但不能同時連到兩者。 |
| `metro_travels` 到 `payments` | 1:N，可選父交易 | 一筆 metro trip 可以有 payment record。schema 使用 `CHECK` constraint 確保 `booking_id` 和 `trip_id` 只有一個有值。 |
| `national_rail_bookings` 到 `feedback` | 1:N，可選父交易 | feedback 可以附加在 rail booking 或 metro trip 上。 |
| `metro_travels` 到 `feedback` | 1:N，可選父交易 | feedback 可以附加在 metro trip 或 rail booking 上。 |

這個 ER model 和 `databases/relational/queries.py` 中的 application query functions 對齊，能支援班次查詢、票價計算、座位查詢、自動選位、訂票、取消訂票、使用者歷史紀錄、付款查詢、登入註冊與回饋資料管理。

---

## Section 2 — Normalisation Justification

### 整體正規化策略

TransitFlow 的 relational schema 主要以 3NF 為目標。設計重點是避免把需要被 SQL 查詢使用的重複資料或巢狀資料直接存在大型 JSON 欄位中。這點對本系統很重要，因為 AI assistant 需要經常查詢「哪些 schedules 同時服務起點和終點」、「origin 是否在 destination 前面」、「旅程經過幾站」、「某個 fare class 的票價是多少」、「某日期某班車還有哪些座位可用」以及「某筆 booking 屬於哪個 user」。

大多數資料表使用 mock data 中原本就存在的自然識別碼作為 primary key，例如 `MS01`、`NR01`、`NR_SCH01`、`RU01`、`BK001`。在此教學資料集中，這些欄位都是 candidate key，因為它們能唯一識別 station、schedule、user 或 booking，而且也會直接出現在使用者問題與 seed data 中。保留這些 natural keys 可以避免多一層不必要的 surrogate key lookup。

### 3NF 設計決策一：將 Schedule Stops 拆成 Junction Tables

最重要的 3NF 設計決策，是把 schedule stops 拆成 `metro_schedule_stops` 和 `national_rail_schedule_stops`，而不是把 `stops_in_order` 或 `travel_time_from_origin_min` 直接存在 `metro_schedules` / `national_rail_schedules` 的 array 或 JSON 欄位中。

對 metro schedules 來說，functional dependency 是：

```text
(schedule_id, station_id) -> stop_order, travel_time_from_origin_min
```

對 national rail schedules 來說，functional dependency 是：

```text
(schedule_id, station_id) -> stop_order, travel_time_from_origin_min, is_passed_through
```

這些 attributes 依賴的是整個 composite key，而不是只依賴 `schedule_id` 或只依賴 `station_id`。同一個 station 可能出現在不同 schedules 中，而且站序與從起點出發的 travel time 會依 schedule 而改變。因此，把 stop-specific facts 放在 junction table 中，可以移除 repeating groups，並避免 partial dependency，符合 2NF / 3NF。

這個設計也讓 `query_national_rail_availability()` 和 `query_metro_schedules()` 更容易實作。查詢可以把 stop table join 兩次：一次代表 origin stop，一次代表 destination stop，然後用 `origin_stop.stop_order < destination_stop.stop_order` 判斷行進方向是否正確。如果 stops 只存在 JSON array 中，SQL 就必須解析 JSON，foreign key constraint 也比較難保證資料正確性。

### 3NF 設計決策二：將 National Rail Fares 獨立成資料表

Rail fare 被獨立存在 `national_rail_fares` 中，並使用 (`schedule_id`, `fare_class`) 作為 composite primary key。其 functional dependency 是：

```text
(schedule_id, fare_class) -> base_fare_usd, per_stop_rate_usd
```

票價不是單純依賴 `schedule_id`，因為同一個 schedule 可以有 `standard` 和 `first` 等不同 fare classes。票價也不是單純依賴 `fare_class`，因為不同 schedules 的 `standard` 或 `first` 可能有不同 base fare 和 per-stop rate。因此，將 fare rules 拆成獨立資料表可以避免在 `national_rail_schedules` 中重複放置多組 fare 欄位，也讓 `query_national_rail_fare()` 可以先查出 fare rule，再根據 `stops_travelled` 計算總票價。

### 3NF 設計決策三：Seat Layout 與 Individual Seats 分離

原始資料中的 seat layout 是巢狀結構，包含 coaches 和 seats。schema 將它拆成 `national_rail_seat_layouts` 與 `national_rail_seats`。對 individual seat row 來說，functional dependency 是：

```text
(schedule_id, seat_id) -> layout_id, coach, fare_class, row_number, seat_column
```

這樣設計可以避免把整個座位表作為 nested array 存在 schedule table 中，也讓 seat availability query 更精準。`query_available_seats()` 可以直接用 schedule、travel date、fare class 和已存在 bookings 比對每個座位是否可用。如果只儲存座位數量，系統只能知道還剩幾個座位，無法回傳實際的 coach、row、column，也無法支援使用者指定座位或自動選擇相鄰座位。

### User Profile 與 Password Credentials 分離

`registered_users` 儲存使用者基本資料，例如姓名、email、電話、生日與帳號狀態；`user_password_credentials` 則儲存 authentication data，例如 `password_hash` 和 `password_updated_at`。兩者是 1:1 relationship，因為 `user_password_credentials.user_id` 同時是 primary key，也是 foreign key，指向 `registered_users.user_id`。

這個設計能降低 transitive security risk。使用者的 profile attributes，例如 `full_name`、`email`、`phone`，不應該和 `password_hash` 混在同一個表中。雖然它們都依賴 `user_id`，但用途和存取權限不同。在 production system 中，credentials table 可以設定更嚴格的權限與稽核規則，而 profile table 可以提供給較多查詢功能使用。

### Deliberate Denormalisation / Trade-offs

整體 schema 以正規化為主，但有幾個地方刻意保留 denormalisation，原因是歷史紀錄穩定性與系統簡化：

1. `national_rail_bookings` 會儲存 `origin_station_id`、`destination_station_id`、`stops_travelled`、`amount_usd` 和 `departure_time`。這些資料有些可以從 schedule stop 和 fare table 推導出來，但 booking 是歷史交易紀錄。如果未來 timetable 或 fare rule 改變，舊 booking 仍然應該保留使用者當時購買的票價、出發時間與旅程端點。
2. `metro_travels` 也儲存 `origin_station_id`、`destination_station_id`、`stops_travelled` 和 `amount_usd`。這讓使用者 travel history 不會因為 schedule table 後續修改而改變。
3. `payments` 和 `feedback` 使用兩個 nullable foreign keys：`booking_id` 和 `trip_id`，並透過 `CHECK` constraint 確保剛好只有其中一個有值。更完全正規化的作法是建立一個 shared parent transaction table，再讓 rail bookings 和 metro trips 都 reference 它。但在這個教育專案中，BK 和 MT 兩種 transaction type 很明確，用兩個 FK 加上 constraint 可以維持 referential integrity，同時避免過度複雜化 schema。

這些 trade-offs 是刻意做出的。schema 仍保留 foreign key、primary key 和 check constraint 的資料完整性，但同時讓 booking history、payment history 和 user-facing query 更容易維護。

### Password Hashing 設計

最終實作在 `databases/relational/queries.py` 中使用 Argon2id，也就是 `argon2.PasswordHasher(type=Type.ID)`。`skeleton/seed_postgres.py` 在匯入 mock users 時也會先將 plain-text password hash 後，再寫入 `user_password_credentials.password_hash`。因此資料庫中保存的是 password hash，不是明文密碼。

Argon2id 比 MD5、SHA-1 或單純 SHA-256 更適合 password hashing，原因是 password hashing 需要刻意提高每次猜密碼的成本。MD5 和 SHA-1 是快速 hash algorithm，攻擊者如果取得 hash，可以用 GPU 或專用硬體快速嘗試大量 dictionary / brute-force guesses。Argon2id 則使用 key stretching 和 memory-hard computation，讓每次猜測都需要更多 CPU time 和 memory，因此能有效降低暴力破解速度。

Salt 的管理由 Argon2 hash string 自動處理。每次呼叫 `PasswordHasher.hash()` 時，Argon2 都會產生 random salt，並把 salt 和 hash parameters 一起編碼在最後儲存的 hash string 中。Salt 不需要保密，它的作用是讓兩個使用相同密碼的使用者也會得到不同 hash。舉例來說，如果兩個 user 都使用 `password123`，Argon2id 仍會因為 salt 不同而產生不同 hash，攻擊者就不能直接用 rainbow table 查出所有相同密碼的帳號。

登入時，`login_user()` 會從 `user_password_credentials` 讀出 stored Argon2id hash，並用 `_PASSWORD_HASHER.verify(...)` 驗證使用者輸入的 password。更新密碼時，`update_password()` 也會先 hash 新密碼再更新 credential row。這確保 plain-text password 不會被永久儲存在資料庫中。

### 資料庫術語總結

此 schema 在需要完整 functional dependency 的地方使用 composite primary key，例如 (`schedule_id`, `station_id`) 決定 schedule stop 的 `stop_order` 和 `travel_time_from_origin_min`，以及 (`schedule_id`, `fare_class`) 決定 fare rule 的 `base_fare_usd` 和 `per_stop_rate_usd`。這避免了 partial dependency。使用者 profile 和 credentials 分表、fare rules 分表、stops 分表、seats 分表，也避免把不同語意的 attributes 塞在同一個 parent table 中造成 transitive dependency 或 repeating groups。

---

## Section 3 - 圖形資料庫設計理由

TransitFlow 使用 Neo4j 建立城市捷運與國鐵網路的實體連接模型。在圖形資料庫中，車站被儲存為節點（nodes），車站之間可通行的直接連線被儲存為關係（relationships），而車站名稱、路線與行駛時間等細節則儲存為屬性（properties）。此模型符合本系統的主要路線查詢需求，包括尋找最快路線、最便宜路線、避開關閉車站的替代路線、跨捷運與國鐵的轉乘路線，以及分析延誤可能影響的鄰近車站。

### 節點、關係與屬性的設計

圖形資料庫包含兩種主要車站節點：

- `MetroStation`：代表城市捷運車站，例如 `MS01`、`MS07` 和 `MS15`。
- `NationalRailStation`：代表國鐵車站，例如 `NR01`、`NR03` 和 `NR07`。

車站適合設計為節點，因為每一段旅程都會從某個車站開始，並在另一個車站結束；車站也是路線分支或轉乘發生的位置。`metro_stations.json` 與 `national_rail_stations.json` 為每個車站提供獨立的識別碼、名稱、服務路線、轉乘資訊及相鄰車站。這些資料描述的是車站本身，因此應儲存在節點及其屬性中。

每個節點以 `station_id` 作為唯一識別屬性。專案中的關聯式資料表、排班、訂票資料、Graph query 和 Agent 工具參數都使用 `station_id` 識別車站。捷運車站使用 `MS01` 至 `MS20`，國鐵車站則使用 `NR01` 至 `NR10`。車站名稱可能變更或重複，因此不適合作為唯一識別；`station_id` 較穩定、簡短，也能與其他資料庫中的車站資料一致。

圖形模型使用以下主要關係：

- `METRO_LINK`：連接兩個相鄰的捷運車站。
- `RAIL_LINK`：連接兩個相鄰的國鐵車站。
- `INTERCHANGE_TO`：連接可以互相轉乘的捷運與國鐵車站。

直接軌道連線適合儲存為關係，因為路線搜尋的核心就是沿著連線從一個車站移動至另一個車站。例如，`MS01` 與 `MS05`、`MS02`、`MS06`、`MS07` 直接相連，而 `NR01` 與 `NR02`、`NR06` 直接相連。這些連線不是單一車站自己的屬性，而是兩個車站之間可以被走訪的關係。將其設計為 Neo4j relationship，可以讓資料庫直接沿著相關連線進行 traversal，而不需要反覆 join 車站資料表。

關係屬性主要包括 `line` 和 `travel_time_min`。`line` 應放在關係上，因為一個車站可能服務多條路線，但某一段車站連線通常屬於特定路線。`travel_time_min` 也應放在關係上，因為它代表從一個車站移動至另一個相鄰車站所需的成本，而不是任何單一車站本身的屬性。若要支援最便宜路線查詢，也可以在關係上儲存或計算 `fare` 權重，讓同一個圖形結構可以依時間或費用進行最佳化。

節點屬性包括 `station_id`、`name`、`lines`，以及 `is_interchange_metro`、`is_interchange_national_rail` 等轉乘標記。這些屬性可以用於篩選和說明查詢結果。例如，系統可以根據資料說明 `MS01` Central Square 可以轉乘至 `NR01` Central Station，而 `MS15` Ferndale 可以轉乘至 `NR07` Ferndale Halt。

### 為何路線查詢適合使用圖形資料庫

PostgreSQL 適合儲存結構化與交易型資料，例如使用者、排班、座位、訂票及付款紀錄。然而，路線搜尋本質上是一個圖形走訪問題。為了找到兩個車站之間的最快路徑，系統需要持續探索相鄰車站、累計各段行駛時間，並避免重複走訪無效路徑。在 Neo4j 中，車站與連線已直接表示為 nodes 和 relationships，因此 Dijkstra 最短路徑演算法可以使用 relationship 的 `travel_time_min` 作為權重。

如果使用關聯式資料庫實作相同功能，通常需要使用 recursive CTE 遞迴查詢車站連線。SQL 查詢需要自行保存目前路徑、累計時間、已走訪車站、終止條件及防止循環的邏輯。當需求增加為「避開某個車站」或「只透過指定轉乘站跨越捷運與國鐵」時，SQL 會變得更複雜，也更難維護與調整。

Neo4j 較適合 TransitFlow，因為實體交通網路本身就是一個圖。BFS 和 Dijkstra 等圖形演算法可以直接在此結構上執行。例如，當使用者詢問「從 MS01 到 MS14 最快怎麼走？」或「如何從 MS03 前往 NR05？」時，圖形資料庫可以從起點節點沿著關係走訪至終點，並最小化總行駛時間。PostgreSQL 仍負責儲存精確的班次與票價，但 Neo4j 更適合發現車站之間的可行路徑。

### 圖形模型支援的查詢類型

第一種查詢是最快路線搜尋。Agent 的 `find_route` 工具會呼叫 `query_shortest_route(origin_id, destination_id)`。此查詢先利用 `station_id` 找到起點與終點節點，再沿著 `METRO_LINK`、`RAIL_LINK`，以及需要時的 `INTERCHANGE_TO` 關係進行走訪。Dijkstra 演算法以 `travel_time_min` 作為權重，最後回傳依序經過的車站、每一段路線、路線名稱與總行駛時間。

第二種查詢是跨網路轉乘路線。原始資料中已有捷運與國鐵之間的轉乘配對，例如 `MS01` 與 `NR01`、`MS07` 與 `NR03`，以及 `MS15` 與 `NR07`。將這些配對建立為 `INTERCHANGE_TO` relationships 後，Neo4j 可以自然地搜尋從捷運起點前往國鐵終點的完整路徑，不需要由 Python 額外將兩段不同網路的路線手動組合。

第三種查詢是避開關閉或延誤車站的替代路線。`find_alternative_routes` 工具可以搜尋不包含指定 `avoid_station_id` 節點的路徑。在圖形資料庫中，這可以作為 path traversal 的限制條件。相較之下，SQL recursive CTE 必須自行維護已走訪節點陣列並排除包含關閉車站的路徑，因此實作較複雜。

第四種查詢是延誤漣漪分析。`get_delay_ripple` 工具可以從延誤車站出發，使用有深度限制的 BFS 找出 `N` hops 內的所有車站。直接相連的車站可能最先受到影響，而距離兩個以上 hops 的車站可能受到後續延誤。這類查詢所使用的是網路距離，而不是地理或字母順序，因此很適合使用 graph traversal。

## Section 4 - 向量資料庫與 RAG 設計

TransitFlow 使用 PostgreSQL 的 pgvector extension 儲存及搜尋政策文件。當使用者詢問退款、延誤賠償、訂票規則、票種、行李、單車、寵物或乘車規範時，系統會從向量資料庫中找出語意最相關的文件，再交由 LLM 產生答案。

### 被嵌入的資料及設計理由

向量資料來自 `train-mock-data/` 中的四個 JSON 文件：

- `refund_policy.json`
- `ticket_types.json`
- `booking_rules.json`
- `travel_policies.json`

`skeleton/seed_vectors.py` 會把每一筆退款政策、每一種票種、每一個訂票規則區段，以及每一個乘車政策區段建立成獨立文件。每份文件會儲存在 `policy_documents` 資料表中，欄位包括 `title`、`category`、`content`、`source_file` 和 `embedding`。

政策文件適合轉換成 embeddings，因為使用者通常不會使用與原始文件完全相同的文字。例如，使用者可能詢問「火車遲到 45 分鐘可以拿回多少錢？」，但政策文件中的用詞可能是「delay compensation」。向量搜尋可以比較兩段文字的語意，而不是只比對是否包含相同關鍵字，因此可以找出措辭不同但意思相近的政策。

本專案使用 cosine similarity，因為 embedding 搜尋主要關心向量在語意空間中的方向，而不是向量的大小。即使兩段文字長度不同，只要意思相近，其 embedding 方向仍應相似。pgvector 使用 `<=>` 運算子計算 cosine distance，而程式以 `1 - (embedding <=> query_vector)` 將距離轉換為 similarity。系統再依距離由小至大，也就是相似度由高至低排序，並使用設定的 similarity threshold 過濾不相關結果。

### 完整 RAG 流程

TransitFlow 的 RAG pipeline 如下：

1. 在建立向量資料時，`skeleton/seed_vectors.py` 讀取四個政策 JSON 文件，並將每一筆政策或區段轉換成文字。
2. Seeder 呼叫 `llm.embed(document_content)`，使用目前設定的 embedding provider 將文件轉換成向量。
3. `store_policy_document()` 將文件文字、metadata 與 embedding 儲存至 PostgreSQL 的 `policy_documents` 資料表。
4. 當使用者提出政策問題時，Agent 會根據問題內容選擇 `search_policy` 工具。
5. `search_policy` 使用 `llm.embed(params["query"])` 將使用者問題轉換成 query embedding。
6. `query_policy_vector_search()` 在 `policy_documents` 上執行 pgvector cosine similarity search。
7. 系統依相似度回傳最相關的文件。預設 `VECTOR_TOP_K` 為 3，並使用 `VECTOR_SIMILARITY_THRESHOLD` 排除相似度過低的文件。
8. 搜尋結果包含文件的 `title`、`category`、`content` 和 `similarity`，並被傳回 Agent。
9. Agent 將使用者原始問題與檢索到的政策內容一起放入 LLM prompt，讓 LLM 根據實際政策資料產生最終答案。

此流程稱為 Retrieval-Augmented Generation，因為 LLM 並不是只依靠原本的模型知識回答問題。系統會先從 TransitFlow 自己的政策資料庫檢索相關內容，再利用檢索結果產生有資料依據的答案，降低模型憑空產生政策資訊的風險。

### Embedding 維度選擇與切換 Provider 的影響

目前 `databases/relational/schema.sql` 將 `policy_documents.embedding` 定義為 `vector(768)`。這是因為專案預設使用 Ollama 的 `nomic-embed-text` 模型，而 `skeleton/config.py` 中的 `OLLAMA_EMBED_DIM` 也是 768。因此，目前專案實際採用的 embedding dimension 為 768。

專案也支援 Gemini 的 `gemini-embedding-001`，其 embedding dimension 為 3072。如果團隊改用 Gemini，必須把 schema 改為 `embedding vector(3072)`，重設 PostgreSQL Docker volume，然後重新執行 `skeleton/seed_vectors.py` 建立所有文件向量。

如果在完成 seeding 後直接切換 embedding provider，已儲存的向量索引將無法繼續使用。768 維的 Ollama query vector 無法與 3072 維的 Gemini document vectors 比較；同樣地，3072 維的 Gemini query vector 也無法與 768 維的 Ollama document vectors 比較。實際執行時會發生 embedding dimension mismatch 錯誤。

因此，團隊必須在 vector seeding 前決定使用同一個 embedding provider。若之後切換 provider，除了修改 schema 的向量維度外，也必須清除舊資料並重新建立 policy embeddings 與 HNSW cosine similarity index。只在 UI 中切換聊天模型不一定會改變 embedding provider；真正需要重建索引的是啟動設定所使用的 embedding model 發生變更時。

---

## Section 5 — AI Tool Usage Evidence

### Example 1 — Relational Schema Normalisation

**Context:**  
我們需要檢查 relational schema 是否符合評分標準，特別是 timetable stop order 不能只存在 JSON array 裡，而應該用正規化的資料表表示。

**Prompt:**  
請根據 student guide 檢查 `schema.sql`、`seed_postgres.py`、`queries.py`，看看 schedule stops 的設計是否符合 3NF，以及查詢函式能不能正確判斷 origin 和 destination 的順序。

**Outcome:**  
AI 指出原本把 `stops_in_order` 存成 JSONB 會不符合 rubric 中對 normalisation 的要求。這個問題是透過比對 student guide 中「schedule stops should be in a separate junction table」的要求發現的。修正方式是新增 `metro_schedule_stops` 和 `national_rail_schedule_stops`，用 `schedule_id`、`station_id`、`stop_order`、`travel_time_from_origin_min` 來表示每個 schedule 的站序，並同步更新 seed 和 query 程式。

---

### Example 2 — Debugging Booking Transaction Logic

**Context:**  
`execute_booking()` 必須同時建立 booking 和 payment，而且要在同一個 transaction 裡完成，否則可能出現 booking 成功但 payment 沒有建立的資料不一致問題。

**Prompt:**  
請根據 live testing rubric 檢查 `execute_booking()`，確認它是否在同一個 transaction 中建立 booking 和 payment，也檢查重複座位是否有正確阻擋。

**Outcome:**  
AI 發現兩個具體錯誤。第一，原本的 `execute_booking()` 只新增 `national_rail_bookings`，沒有新增 `payments`，不符合 live testing rubric 對 atomic booking/payment transaction 的要求。第二，原本只檢查 `confirmed` 狀態的座位，導致 `completed` booking 的座位可能被重複訂。這些問題是透過閱讀程式碼和執行 smoke test 發現的，其中測試嘗試再次預訂已存在 booking 的座位時，系統錯誤地允許訂票。修正方式是讓 `execute_booking()` 在同一個 transaction 中同時 insert booking 和 payment，並把所有非 `cancelled` 的 booking 都視為已佔用座位。

---

### Example 3 — Neo4j Graph Design and Routing

**Context:**  
Neo4j 的 graph schema 需要符合評分文件要求，例如 node labels 要有 `MetroStation` 和 `NationalRailStation`，relationship types 要有 `METRO_LINK`、`RAIL_LINK`、`INTERCHANGE_TO`。

**Prompt:**  
請根據 student guide 檢查 `seed_neo4j.py` 和 `databases/graph/queries.py`，找出 graph schema 或 Cypher query 是否有和評分要求不一致的地方。

**Outcome:**  
AI 發現原本 graph schema 和 rubric 不一致。具體錯誤是原本只使用通用的 `Station` label，以及 `CONNECTS_TO` / `INTERCHANGES_WITH` relationships，但評分文件要求 `MetroStation`、`NationalRailStation`、`METRO_LINK`、`RAIL_LINK`、`INTERCHANGE_TO`。這個問題是透過比對 student guide 的 Neo4j rubric 和現有 Cypher seed/query 發現的。修正方式是更新 `seed_neo4j.py`，讓 station nodes 同時有共用的 `Station` label 和網路專屬 label，並把 relationships 改成 `METRO_LINK`、`RAIL_LINK`、`INTERCHANGE_TO`。相關 query functions 也同步更新為使用新的 relationship types。

---

### Example 4 — Correcting an AI Output Error

**Context:**  
我們請 AI 幫忙檢查 `execute_booking()` 是否符合 live testing rubric，特別是座位是否會被重複預訂。AI 一開始建議只要檢查是否已存在 `confirmed` 狀態的 booking，就可以判斷座位是否被佔用。

**Prompt:**  
請檢查 `execute_booking()` 的座位重複預訂邏輯，確認它是否能阻止同一班車、同一天、同一個座位被重複預訂。

**Outcome:**  
AI 一開始的建議不完整。它只注意到 `confirmed` booking 會佔用座位，但忽略了 `completed` booking 也代表該座位在該日期已經被使用過。這會造成一個錯誤：如果某個座位已有 `completed` booking，系統仍可能允許新的 booking 使用同一個座位。

這個問題是透過 smoke test 發現的。我們測試再次預訂已存在 booking 的座位：


```python
execute_booking(
    user_id="RU01",
    schedule_id="NR_SCH01",
    origin_station_id="NR01",
    destination_station_id="NR05",
    travel_date="2026-04-02",
    fare_class="standard",
    seat_id="B05"
)
```
## Section 6 — Reflection & Trade-offs

我們的一個重要設計決策是把 schedule stops 拆成獨立資料表，而不是只存在 JSON array 中。原始 mock data 裡的 `stops_in_order` 是 array，但在 relational database 中，站序其實是 `(schedule_id, station_id)` 這個組合的屬性。因此我們建立 `metro_schedule_stops` 和 `national_rail_schedule_stops`，用 `stop_order` 表示順序。這樣比較符合 3NF，也讓查詢 origin 是否在 destination 前面變成簡單的數字比較。

第二個設計決策是把 `payments` 和 `feedback` 裡的交易來源拆成 `booking_id` 和 `trip_id`。原始 JSON 用同一個欄位表示 national rail booking (`BK...`) 和 metro trip (`MT...`)，但如果只用一個文字欄位，就無法建立真正的 foreign key。拆成兩個 nullable FK，再用 `CHECK` constraint 確保只能填其中一個，可以保留 referential integrity。

如果這是一個 production system，我們不會用 `docker compose down -v` 來套用 schema changes，因為這會刪掉所有資料。正式環境會使用 migration 工具，例如 Alembic 或 Flyway，逐步套用 schema 版本。同時也會加入 connection pooling、secret management，以及更完整的 monitoring，避免 API key 或資料庫密碼只存在本機 `.env` 中。

---

## Section 7 — Optional Extension: Fewest-Transfers Route Search

### 7.1 Motivation
TransitFlow 原本可以依照最短時間或最低票價推薦路線，但在實際搭乘情境中，乘客不一定只在意速度或價格。對攜帶行李、第一次到訪城市、不熟悉車站結構，或希望降低誤乘風險的乘客來說，「少轉乘」通常比「最快」更重要。

因此，我擴充了 `fewest transfers` 查詢功能，讓 TransitFlow 助理可以根據轉乘次數推薦路線。這讓系統不只是提供技術上可行的路線，而是能更貼近真實乘客的決策方式，提供更穩定、容易理解且風險較低的搭乘建議。

### 7.2 Database Changes
此功能主要使用 Neo4j 圖形資料庫實作。站點會被建模成節點，站與站之間的移動方式會被建模成不同類型的關係。一般行駛路段使用 `METRO_LINK` 或 `RAIL_LINK`，需要步行或換線的轉乘路段則使用 `INTERCHANGE_TO`。

其中 `INTERCHANGE_TO` 是此擴充功能最重要的結構，因為它可以讓系統判斷一條路線中有幾次真正的轉乘。查詢時只要統計路徑中 `INTERCHANGE_TO` 關係的數量，就可以把「轉乘次數」變成可排序的指標。

```cypher
(:Station {
  station_id: STRING,
  name: STRING
})

(:MetroStation {
  station_id: STRING,
  name: STRING,
  line: STRING
})

(:NationalRailStation {
  station_id: STRING,
  name: STRING
})

(:MetroStation)-[:METRO_LINK {
  line: STRING,
  travel_time_min: INTEGER,
  distance_km: FLOAT
}]->(:MetroStation)

(:NationalRailStation)-[:RAIL_LINK {
  line: STRING,
  travel_time_min: INTEGER,
  distance_km: FLOAT
}]->(:NationalRailStation)

(:Station)-[:INTERCHANGE_TO {
  walking_time_min: INTEGER,
  interchange_type: STRING
}]->(:Station)
```
### 7.3 Example Queries
以下是從 MS01 (Central Square) 到 MS09 (Queensbridge) 尋找最少轉乘路線的 Cypher 查詢。它會先找出可行路徑，再計算總時間與轉乘次數，最後優先依照轉乘次數排序。在 LLM 代理中，這會透過工具呼叫 `find_route({'origin_id': 'MS01', 'destination_id': 'MS09', 'optimise_by': 'transfers'})` 來觸發。

```cypher
MATCH p = (origin:Station {station_id: "MS01"})-[rels:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..12]->(destination:Station {station_id: "MS09"})
WITH p, rels,
     reduce(totalTime = 0, r IN rels |
       totalTime + coalesce(r.travel_time_min, r.walking_time_min, 0)
     ) AS total_time_min,
     size([r IN rels WHERE type(r) = "INTERCHANGE_TO"]) AS transfers
RETURN
  [n IN nodes(p) | n.station_id] AS path,
  total_time_min,
  transfers
ORDER BY transfers ASC, total_time_min ASC
LIMIT 1;
```
### 7.4 測試

![圖片描述](https://i.meee.com.tw/JVEfGmy.png)

![圖片描述](https://i.meee.com.tw/9V0kxoH.png)

---


