# Peer Review Report

> **Instructions:** Complete this form **individually and independently**.
> Do not discuss your ratings with teammates before submitting.
> Submit via EEClass as a **separate, confidential submission** — not in the shared team repo.
> Your teammates will not see this report.
>
> Reference the team's `WORK_ALLOCATION_TEMPLATE.md` when completing this form.

---

## Your Details

| Field | Your answer |
|-------|------------|
| Full Name | 吳哲寬 |
| Student ID | 112401018 |
| Team ID | 21 |
| Date submitted | 2026/06/06 |

---

## Rating Scale

| Rating | Meaning |
|--------|---------|
| **5** | Exceeded expectations — delivered more than agreed; helped teammates; consistently high quality |
| **4** | Met expectations fully — delivered exactly what was agreed; on time; good quality |
| **3** | Mostly met expectations — minor shortfalls; one or two items completed late or with help |
| **2** | Partially met expectations — noticeable gaps; teammates had to cover some tasks |
| **1** | Did not meet expectations — significant tasks left incomplete; very limited contribution |

---

## Section A — Self-Assessment

### A1. What did you personally implement?

List the specific tasks, functions, files, or document sections that you were the primary author of.
Be specific (e.g., "I designed all 12 tables in schema.sql and implemented query_national_rail_availability and execute_booking").

> *Your answer:*
>
> 我主要負責 PostgreSQL 關聯式資料庫的 schema 設計與資料匯入流程。具體來說，我在 `databases/relational/schema.sql` 設計並建立 metro / national rail station、schedule、schedule stops、fare、seat layout、user、booking、metro travel、payment、feedback 等核心資料表，包含 primary key、foreign key、CHECK constraint、關聯拆表與資料正規化設計。
>
> 我也主要實作 `skeleton/seed_postgres.py`，把 `train-mock-data/` 中的 JSON mock data 依照外鍵相依順序匯入 PostgreSQL，包括 metro stations、national rail stations、metro schedules、national rail schedules、seat layouts、registered users、bookings、metro travel history、payments、feedback。這部分也包含 bulk insert、`ON CONFLICT DO NOTHING` 的 idempotent seeding、使用 Argon2 hash 使用者密碼、將 BK/MT 交易資料拆成 booking/trip foreign key，以及最後的 `verify_counts()` row count 檢查。

---

### A2. What challenges did you face?

Describe any technical or collaboration difficulties you personally encountered and how you resolved them.

> *Your answer:*
>
> 我遇到的主要技術挑戰最大的是商業邏輯要想得很清楚才可以寫好schema，還有原始 mock data 有些欄位比較像巢狀 JSON 或多型資料，例如 schedule stops、fare class、seat layout、payments 同時可能對應 national rail booking 或 metro trip。為了讓後續 SQL 查詢比較穩定，我把這些資料拆成較符合 3NF 的表格，例如 schedule stops、national rail fares、seat rows，以及 payments / feedback 中分開保存 booking_id 和 trip_id。
>
> 另一個挑戰是 seeding 順序與外鍵約束，如果先匯入 child table 會造成 foreign key error。我透過整理 dependency order、把匯入包在 transaction 裡、加入 `ON CONFLICT DO NOTHING` 和 count verification，讓資料庫可以重複 seed 並方便團隊驗證結果。

---

### A3. Self-rating

| Criterion | Rating (1–5) | Justification (1–2 sentences) |
|-----------|-------------|-------------------------------|
| I delivered the tasks assigned to me in the work allocation | 5 | 我完成了關聯式資料庫 schema 設計與 PostgreSQL seeding 的主要工作，並有透過 commit `feat: define schema`、`feat: seed data`、`chore: verify counts` 留下可追蹤紀錄。後續仍有部分 schema/query 相容問題由隊友協助修正。 |
| The quality of my work was satisfactory | 4 | 我的 schema 有外鍵、約束、拆表與 idempotent seed 設計，能支援後續查詢與測試；但整合後仍需要進一步修正 normalisation 和核心查詢邏輯，因此給 4 分。 |
| I communicated well and kept the team informed | 4 | 我有建立 develop branch、提交 AI context/dev file，並把 schema 與 seed 的工作推到分支讓隊友能接續開發。整體溝通可以支援團隊整合，但仍有可更早同步介面細節的空間。 |
| I met deadlines agreed within the team | 4 | 我在專案前中期完成 schema 與 seed，讓後續 relational query、graph query 和 agent 整合可以繼續進行。 |
| **Overall self-rating** | 5 | 我的主要工作完整且是專案基礎之一，但整合階段仍仰賴隊友做修正與補強，因此整體評為符合期待。 |

---

### A4. Estimated contribution percentage

What percentage of the total team effort do you estimate you personally contributed?

> My estimated contribution: **35%**

---

## Section B — Peer Assessments

Complete one subsection per teammate. Add or remove subsections to match your team size.
If your team has 2 members, complete B1 only. If 3 members, complete B1 and B2.

---

### B1. Assessment of Teammate 1

| Field | Your answer |
|-------|------------|
| Teammate's full name | 林守毅 |
| Teammate's student ID | 112401047 |

#### What did this teammate deliver?

List the tasks, functions, files, or document sections that this teammate was the primary author of,
based on what you observed during the project (compare against the work allocation).

> *Your answer:*
>
> 林守毅主要負責 Neo4j graph database 相關功能與整合修正。他在 `skeleton/seed_neo4j.py` 建立 graph network links，並在 `databases/graph/queries.py` 實作 route / network query 模組，包含 `query_shortest_route`、`query_cheapest_route`、`query_alternative_routes`、`query_interchange_path`、`query_delay_ripple`、`query_station_connections`，後續也補上 `query_fewest_transfers_route` 這類延伸功能。
>
> 除了 graph 部分，他也處理了多個整合修正，例如 schema normalisation、核心 relational query 邏輯修正、agent tool routing / result normalisation，以及 RAG / LLM model 設定修正。最後也有補上 schema 和 seeding 檔案中的註解，讓程式更容易被助教與隊友理解。

#### Did their actual contribution match the agreed work allocation?

> *Your answer (Yes / Mostly / Partially / No — with explanation):*
>
> Yes。依照 commit history 和 final codebase 來看，他完成 graph database 的主要工作，也額外承擔整合 debug、RAG/LLM 設定與註解補強，實際貢獻有超出單純 graph task 的範圍。

#### Peer rating for this teammate

| Criterion | Rating (1–5) | Justification (1–2 sentences) |
|-----------|-------------|-------------------------------|
| Delivered the tasks assigned in the work allocation | 5 | 他完成 Neo4j seeding 與 graph query 的主要功能，並額外處理 schema、agent、RAG/LLM 的整合問題。 |
| Quality of their work was satisfactory | 5 | graph query 有考慮 shortest path、alternative route、interchange、delay ripple 等情境，後續修正也改善了整體可用性。 |
| Communicated well and kept the team informed | 4 | 從分支 merge 與多次修正來看，他有持續同步並支援整合；若能更早把接口需求文件化會更好。 |
| Met deadlines agreed within the team | 4 | 他在後期完成多項修正與補強，讓 develop branch 的整體功能更完整。 |
| **Overall rating for this teammate** | 5 | 他除了完成負責範圍，也承擔不少跨模組整合與 bug fix，對最終成果影響很大。 |

#### Estimated contribution percentage for this teammate

> My estimate of their contribution: **35%**

---

### B2. Assessment of Teammate 2

| Field | Your answer |
|-------|------------|
| Teammate's full name | 黃璿羽 |
| Teammate's student ID | 112707530 |

#### What did this teammate deliver?

> *Your answer:*
>
> 黃璿羽主要負責 PostgreSQL relational query functions，在 `databases/relational/queries.py` 完成大量查詢與交易相關功能。從 final codebase 來看，這些功能包含 national rail availability / fare、metro schedules / fare、available seats、auto-select adjacent seats、user profile、user bookings、payment info、booking execution、cancellation、registration/login/password reset，以及 policy vector search / document storage 等與 agent 工具直接相連的函式。
>
> 這些 relational query functions 是 AI assistant 回答班次、票價、座位、訂票、取消訂票、使用者歷史紀錄與 RAG policy search 的主要資料來源，因此對使用者互動功能有很高影響。

#### Did their actual contribution match the agreed work allocation?

> *Your answer (Yes / Mostly / Partially / No — with explanation):*
>
> 大部分。她完成了 relational query 的主要實作，範圍很大且直接支援 assistant 的功能。不過後續有部分 schema normalisation 和核心 query logic 需要隊友協助修正，所以我評為大部分。

#### Peer rating for this teammate

| Criterion | Rating (1–5) | Justification (1–2 sentences) |
|-----------|-------------|-------------------------------|
| Delivered the tasks assigned in the work allocation | 4 | 她完成 `databases/relational/queries.py` 中大部分 relational query 與 booking/user 相關功能，符合主要分工。 |
| Quality of their work was satisfactory | 4 | 功能範圍完整且能支援 agent 使用，但後續仍有一些核心查詢與 schema 對齊問題需要修正。 |
| Communicated well and kept the team informed | 4 | 她有透過自己的分支提交並與其他分支 merge，讓團隊能把 relational query 整合進 develop。 |
| Met deadlines agreed within the team | 4 | relational query 在整合階段前完成主要版本，讓 graph、agent 和 final fix 可以接續進行。 |
| **Overall rating for this teammate** | 4 | 整體貢獻完整且重要，雖然整合後仍有修正需求，但達到主要期待。 |

#### Estimated contribution percentage for this teammate

> My estimate of their contribution: **30%**

---

## Section C — Contribution Percentage Summary

All members (including yourself) must sum to 100%.

| Member | Your estimated % | Notes |
|--------|----------------|-------|
| Yourself（吳哲寬） | 35% | 主要負責 PostgreSQL schema、seeding、資料正規化與 count verification。 |
| Teammate 1（林守毅） | 35% | 主要負責 Neo4j graph seeding/query、route functions、RAG/LLM 與整合修正。 |
| Teammate 2（黃璿羽） | 30% | 主要負責 PostgreSQL relational query functions、booking/user/payment/policy search 相關功能。 |
| **Total** | **100%** | |

---

## Section D — Overall Team Reflection

### D1. What went well in the team's collaboration?

> *Your answer (2–4 sentences):*
>
> 我在一開始便有用codex掃過一整個codebases，模擬三個人一組應該如何切分工作推進，也教他們如何用agent, codex, claude開發，有把三種資料庫的工作切分得滿清楚：我負責 PostgreSQL schema / seed，黃璿羽負責 relational query，林守毅負責 graph query 與後續整合修正。這樣的分工讓大家可以平行開發，也讓 final codebase 能同時支援關聯式資料、圖資料與 RAG policy search。後期 merge 到 develop 後，隊友也有持續修正跨模組相容問題，讓整體功能更完整。

---

### D2. What would you do differently if you did this project again?

> *Your answer (2–4 sentences):*
>
> 如果重做一次，我會更早和隊友明確定義 schema 與 query function 的介面，例如每個欄位名稱、回傳格式、錯誤處理和 agent tool 需要的資料形狀。這樣可以減少後期 schema normalisation 和核心 query logic 的修正成本。我也會更早建立簡單 integration tests，確保 seed 完後每個主要 query 都能直接跑通。

---

### D3. Is there anything else the markers should know about team dynamics or individual contributions?

This is optional. Use it only if there is important context that the ratings above do not capture
(e.g., a member had a documented personal emergency, or a member was unresponsive for a significant period).

> *Your answer (or "Nothing to add"):*
>
> Nothing to add.

---

## Declaration

I confirm that this peer review reflects my honest and independent assessment.
I understand it will be kept confidential from my teammates.

**Signed:** 吳哲寬 **Date:** 2026/06/06
