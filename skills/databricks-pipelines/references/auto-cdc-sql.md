Auto CDC in Declarative Pipelines processes change events from streaming sources or derives changes by comparing complete snapshots.

## Streaming change-event sources

**API Reference:**

**CREATE FLOW ... AS AUTO CDC INTO**
Applies CDC operations (inserts, updates, deletes) from a streaming source to a target table. Supports SCD Type 1 (latest) and Type 2 (history). Must be used with a pre-created streaming table.

```sql
CREATE OR REFRESH STREAMING TABLE <target_table>;

CREATE FLOW <flow_name> AS AUTO CDC INTO <target_table>
FROM <source>
KEYS (<key1>, <key2>)
[IGNORE NULL UPDATES [ON {<column_list> | * EXCEPT (<except_column_list>)}]]
[APPLY AS DELETE WHEN <condition>]
[APPLY AS TRUNCATE WHEN <condition>]
SEQUENCE BY <sequence_column>
[SYSTEM SEQUENCE BY <system_sequence_column>]
[COLUMNS {<column_list> | * EXCEPT (<except_column_list>)}]
[COLUMNS TO UPDATE <status_column>]
[STORED AS {SCD TYPE 1 | SCD TYPE 2 | BITEMPORAL}]
[TRACK HISTORY ON {<column_list> | * EXCEPT (<except_column_list>)}]
```

Parameters:

- `target_table` (identifier): Target table name (must exist, create with `CREATE OR REFRESH STREAMING TABLE`). **Required.**
- `flow_name` (identifier): Identifier for the created flow. **Required.**
- `source` (identifier or expression): Streaming source with CDC events. Use `STREAM(<table_name>)` to read with streaming semantics. **Required.**
- `KEYS` (column list): Primary key columns for row identification. **Required.**
- `IGNORE NULL UPDATES` (optional): If specified, NULL values won't overwrite existing non-NULL values. Add `ON (col1, col2)` to ignore NULLs for only a subset of columns (all others apply NULLs), or `ON * EXCEPT (col1, col2)` for the inverse.
- `APPLY AS DELETE WHEN` (optional): Condition identifying delete operations (e.g., `operation = 'DELETE'`)
- `APPLY AS TRUNCATE WHEN` (optional): Condition identifying truncate operations (supported only for SCD Type 1)
- Clause order matters: put `APPLY AS DELETE WHEN` and `APPLY AS TRUNCATE WHEN` **before** `SEQUENCE BY`, or the parser fails.
- `SEQUENCE BY` (column or struct): Column for ordering events (timestamp, version). **Required.** For multi-column sequencing, use `SEQUENCE BY STRUCT(timestamp_col, id_col)` to order by the first field first, then break ties with subsequent fields.
- `SYSTEM SEQUENCE BY` (column): System-time sequencing column. **Required when `STORED AS BITEMPORAL`**; not used otherwise
- `COLUMNS` (optional): Columns to include or exclude (use `column1, column2` or `* EXCEPT (column1, column2)`). Only list columns that exist in the source; for example, omit `_rescued_data` from `* EXCEPT` unless the source actually has it.
- `COLUMNS TO UPDATE <status_column>` (optional): For partial updates — names a source column of type `ARRAY<STRING>` listing, per change record, exactly which columns to write. Listed columns are written (including explicit NULLs); unlisted columns keep their existing value. Mutually exclusive with `IGNORE NULL UPDATES`; not supported with `STORED AS BITEMPORAL`. See Pattern 12.
- `STORED AS` (optional): `SCD TYPE 1` for latest values (default), `SCD TYPE 2` for full history with `__START_AT`/`__END_AT` columns, or `BITEMPORAL` for two-axis history (Beta, DBR 17.3+) — see Pattern 11
- `TRACK HISTORY ON` (optional): For SCD Type 2, columns to track history for (others use Type 1)

**Common Patterns:**

**Pattern 1: Basic CDC flow from streaming source**

```sql
-- Step 1: Create target table
CREATE OR REFRESH STREAMING TABLE users;

-- Step 2: Define CDC flow using STREAM() for streaming semantics
CREATE FLOW user_flow AS AUTO CDC INTO users
FROM STREAM(user_changes)
KEYS (user_id)
SEQUENCE BY updated_at;
```

**Pattern 2: CDC with source filtering via temporary view**

```sql
-- Step 1: Create temporary view to filter/transform source data
CREATE TEMPORARY VIEW filtered_changes AS
SELECT * FROM STREAM(source_table) WHERE status = 'active';

-- Step 2: Create target table
CREATE OR REFRESH STREAMING TABLE active_records;

-- Step 3: Define CDC flow reading from the temporary view
CREATE FLOW active_flow AS AUTO CDC INTO active_records
FROM STREAM(filtered_changes)
KEYS (record_id)
SEQUENCE BY updated_at;
```

**Pattern 3: CDC with explicit deletes**

```sql
CREATE OR REFRESH STREAMING TABLE orders;

CREATE FLOW order_flow AS AUTO CDC INTO orders
FROM STREAM(order_events)
KEYS (order_id)
IGNORE NULL UPDATES
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY event_timestamp;
```

**Pattern 4: SCD Type 2 (Historical tracking)**

```sql
CREATE OR REFRESH STREAMING TABLE customer_history;

CREATE FLOW customer_flow AS AUTO CDC INTO customer_history
FROM STREAM(customer_changes)
KEYS (customer_id)
SEQUENCE BY changed_at
STORED AS SCD TYPE 2;
-- Target will include __START_AT and __END_AT columns
```

**Pattern 5: Multi-column sequencing**

```sql
CREATE OR REFRESH STREAMING TABLE events;

CREATE FLOW event_flow AS AUTO CDC INTO events
FROM STREAM(event_changes)
KEYS (event_id)
SEQUENCE BY STRUCT(event_timestamp, event_id)
STORED AS SCD TYPE 1;
```

**Pattern 6: Selective column inclusion**

```sql
CREATE OR REFRESH STREAMING TABLE accounts;

CREATE FLOW account_flow AS AUTO CDC INTO accounts
FROM STREAM(account_changes)
KEYS (account_id)
SEQUENCE BY modified_at
COLUMNS account_id, balance, status
STORED AS SCD TYPE 1;
```

**Pattern 7: Selective column exclusion**

```sql
CREATE OR REFRESH STREAMING TABLE products;

CREATE FLOW product_flow AS AUTO CDC INTO products
FROM STREAM(product_changes)
KEYS (product_id)
SEQUENCE BY updated_at
COLUMNS * EXCEPT (internal_notes, temp_field);
```

**Pattern 8: SCD Type 2 with selective history tracking**

```sql
CREATE OR REFRESH STREAMING TABLE accounts;

CREATE FLOW account_flow AS AUTO CDC INTO accounts
FROM STREAM(account_changes)
KEYS (account_id)
IGNORE NULL UPDATES
SEQUENCE BY modified_at
STORED AS SCD TYPE 2
TRACK HISTORY ON balance, status;
-- Only balance and status changes create new history records
```

**Pattern 9: SCD Type 2 with history tracking exclusion**

```sql
CREATE OR REFRESH STREAMING TABLE accounts;

CREATE FLOW account_flow AS AUTO CDC INTO accounts
FROM STREAM(account_changes)
KEYS (account_id)
SEQUENCE BY modified_at
STORED AS SCD TYPE 2
TRACK HISTORY ON * EXCEPT (last_login, view_count);
-- Track history on all columns except last_login and view_count
```

**Pattern 10: Truncate support (SCD Type 1 only)**

```sql
CREATE OR REFRESH STREAMING TABLE inventory;

CREATE FLOW inventory_flow AS AUTO CDC INTO inventory
FROM STREAM(inventory_events)
KEYS (product_id)
APPLY AS TRUNCATE WHEN operation = 'TRUNCATE'
SEQUENCE BY event_timestamp
STORED AS SCD TYPE 1;
```

**Pattern 11: Bitemporal CDC (Beta — two time axes)**

```sql
CREATE OR REFRESH STREAMING TABLE account_balances;

CREATE FLOW balance_flow AS AUTO CDC INTO account_balances
FROM STREAM(balance_changes)
KEYS (account_id)
SEQUENCE BY effective_at          -- business time: when the fact was true
SYSTEM SEQUENCE BY ingested_at    -- system time: when we recorded it (REQUIRED)
STORED AS BITEMPORAL;
-- Adds __START_AT/__END_AT (business time) and
-- __SYSTEM_START_AT/__SYSTEM_END_AT (system time). Out-of-order changes are
-- corrected automatically; old beliefs are closed, never deleted.
```

**Pattern 12: Partial updates (only update the changed columns; apply explicit NULLs)**

```sql
-- When change events carry only the columns that changed (the rest arrive NULL),
-- COLUMNS TO UPDATE names a per-row ARRAY<STRING> status column listing which
-- columns to write. Unlisted columns keep their existing value; explicitly-cleared
-- columns are written as NULL.
CREATE OR REFRESH STREAMING TABLE customers;

CREATE FLOW customer_flow AS AUTO CDC INTO customers
FROM STREAM(customer_changes)
KEYS (id)
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY event_ts
COLUMNS TO UPDATE updatedColumns
STORED AS SCD TYPE 1;
```

To name the subset in code instead of per-row, use `IGNORE NULL UPDATES ON (country)`
(only `country` keeps its existing value on NULL) or
`IGNORE NULL UPDATES ON * EXCEPT (age)` (every column except `age` keeps its existing
value on NULL). Prefer `COLUMNS TO UPDATE` over a blanket `IGNORE NULL UPDATES`, which
cannot apply intentional NULLs.

---

## Snapshot sources

Read [AUTO CDC FROM SNAPSHOT](auto-cdc-from-snapshot.md) for the shared SQL syntax, refresh behavior, two-phase version selection, `ONCE` lifecycle, examples, constraints, and errors.

---

## SCD Type 1 vs Type 2 vs Bitemporal Guide

### Quick Decision

| Question                           | Answer                   |
| ---------------------------------- | ------------------------ |
| Need to query historical values?   | **SCD Type 2**           |
| Only need current/latest state?    | **SCD Type 1**           |
| Need to deduplicate incoming data? | **SCD Type 1**           |
| Need audit trail of changes?       | **SCD Type 2**           |
| Building star schema dimensions?   | **SCD Type 2** (usually) |
| Need as-of-system-time queries?    | **Bitemporal** (Beta)    |
| Source has two timestamps with different semantic meaning? | **Bitemporal** (Beta) |

**Recognizing bitemporal from the source schema.** Users rarely ask for "bitemporal" by name — they describe two timestamps. Whenever the source carries two timestamps with genuinely different semantic meaning, raise bitemporal as an option even if the request never mentions CDC, SCD, or history — including a plain "load this table" ask. Explain the payoff (as-of-system-time queries — "what did we believe at time T?") and let the user choose; do not silently upgrade a plain ingestion request.

The engine's two axes are business time (`SEQUENCE BY`) and system time (`SYSTEM SEQUENCE BY`). The pattern is one timestamp for *when the fact holds in the domain* and another for *when the system learned or recorded it*, which surfaces under many domain vocabularies:

- `effective_at` + `ingested_at`, `event_time` + `load_time`, `as_of_date` + `received_at`
- trade date + booking date; policy effective date + endorsement entry date
- observation/measurement time + chart-entry or lab-report time
- period a correction applies to + the run that issued the correction (restatements, amended filings, retroactive adjustments)
- any "we found out later that the value back then was actually different" framing

Map whichever column means "true in the domain" to `SEQUENCE BY` and whichever means "recorded by us" to `SYSTEM SEQUENCE BY`. If it is unclear which is which, ask rather than guessing.

Two timestamps alone are **not** sufficient. Do NOT use bitemporal when:

- both columns order the *same* axis and exist only to break ties → multi-column sequencing, `SEQUENCE BY STRUCT(ts, id)`
- one is a key/id and the other a timestamp → ordinary SCD Type 1/2
- they are `created_at` + `updated_at` on the same record → ordinary SCD Type 1/2 (the record's own lifecycle, not two independent axes)

Bitemporal requires two *independent* axes: a late-arriving correction must be able to change what was believed at a past business time without changing that business time.

### Comparison

| Aspect                  | SCD Type 1                   | SCD Type 2                     | Bitemporal (Beta)                                           |
| ----------------------- | ---------------------------- | ------------------------------ | ----------------------------------------------------------- |
| History preserved       | No                           | Yes (business time)            | Yes (business + system time)                                |
| `__START_AT`/`__END_AT` | No                           | Yes                            | Yes, plus `__SYSTEM_START_AT`/`__SYSTEM_END_AT`             |
| Storage cost            | Lower                        | Higher                         | Highest                                                     |
| Query complexity        | Simple                       | Needs `WHERE __END_AT IS NULL` | Two-axis filter (see below)                                 |
| Use case                | Deduplication, current state | History, audit, point-in-time  | History, audit, point-in-time, "what did we know and when"  |
| SQL syntax              | `STORED AS SCD TYPE 1`       | `STORED AS SCD TYPE 2`         | `STORED AS BITEMPORAL` + `SYSTEM SEQUENCE BY`               |

### Querying SCD Type 2 Tables

SCD Type 2 tables have multiple rows per key. Use `__START_AT`/`__END_AT` to select the right version. See [scd-2-querying.md](scd-2-querying.md) for more query patterns.

**Current state only:**

```sql
SELECT * FROM dim_customers WHERE __END_AT IS NULL;
```

**Point-in-time lookup (as of a specific date):**

```sql
SELECT * FROM dim_customers
WHERE __START_AT <= '2024-06-01'
  AND (__END_AT > '2024-06-01' OR __END_AT IS NULL);
```

**Temporal join (join facts to the dimension version active at event time):**

```sql
SELECT
  f.order_id,
  f.sale_date,
  f.amount,
  d.customer_name,
  d.region
FROM fact_sales f
JOIN dim_customers d
  ON f.customer_id = d.customer_id
  AND f.sale_date >= d.__START_AT
  AND (f.sale_date < d.__END_AT OR d.__END_AT IS NULL);
```

### Querying Bitemporal Tables

Bitemporal tables carry two validity ranges; filter on both axes.

**Current belief about the current state** (the everyday view):

```sql
SELECT * FROM account_balances WHERE __END_AT IS NULL AND __SYSTEM_END_AT IS NULL;
```

**As-of query — what we believed as of system time `S` about business time `B`:**

```sql
SELECT * FROM account_balances
WHERE __START_AT <= B AND (__END_AT > B OR __END_AT IS NULL)
  AND __SYSTEM_START_AT <= S AND (__SYSTEM_END_AT > S OR __SYSTEM_END_AT IS NULL);
```

### SCD Best Practices

1. **Clean data first** — apply validation and type casting before AUTO CDC
2. **Choose wisely** — use Type 2 only when history is needed (higher storage)
3. **Use TRACK HISTORY ON** — limit version triggers to important columns
4. **Include delete handling** — add `APPLY AS DELETE WHEN` for logical deletes
5. **Meaningful SEQUENCE BY** — use timestamp that reflects true chronological order

---

**KEY RULES:**

- For a standalone named flow, create the target streaming table first. The embedded form creates its target and anonymous flow together.
- For change events, use `FROM STREAM(<table_name>)` and order them with `SEQUENCE BY`.
- For complete snapshots, use `FROM SNAPSHOT (<snapshot_query>)`; use `WITH VERSION` for ordering and do not add flow-level `WHERE` or `SEQUENCE BY`.
- A destination supports at most one snapshot flow; interoperability may additionally allow regular Auto CDC flows on the same target.
- The `STREAM()` function accepts ONLY a table/view identifier - NOT a subquery. Define source data as a separate streaming table or temporary view first, then reference it in the flow
- SCD Type 2 adds `__START_AT` and `__END_AT` columns for validity tracking
- For change-event SCD Type 2 with an explicit schema, `__START_AT` and `__END_AT` must match the `SEQUENCE BY` type.
- For snapshot SCD Type 2, `__START_AT` and `__END_AT` use the version output type; without `WITH VERSION`, the implicit type is `TIMESTAMP`.
- Legacy `APPLY CHANGES INTO` API is equivalent but deprecated - prefer `AUTO CDC INTO`
- SQL supports Auto CDC from periodic snapshots with `AUTO CDC ... FROM SNAPSHOT (...)`.
- **Bitemporal (Beta, DBR 17.3+)**: use `STORED AS BITEMPORAL` with a required `SYSTEM SEQUENCE BY` column. It adds `__SYSTEM_START_AT`/`__SYSTEM_END_AT` on top of `__START_AT`/`__END_AT` — do NOT invent names like `valid_from`/`valid_to`/`txn_from`
- **Offer bitemporal whenever the source has two timestamps with different semantic meaning** — one for when the fact holds in the domain, the other for when the system learned or recorded it — even if the user never says CDC, SCD, history, or bitemporal. Examples include trade vs booking date, observation vs chart-entry time, event time vs recording time. Two timestamps that only break ties on one axis are multi-column sequencing instead; see "Recognizing bitemporal from the source schema" above
- Bitemporal does NOT support `IGNORE NULL UPDATES`, `APPLY AS TRUNCATE`, `TRACK HISTORY ON`, `COLUMNS TO UPDATE`, or multiple flows into the same target
- **Partial updates** (events carrying only the columns that changed): use `COLUMNS TO UPDATE <status_column>` (a per-row `ARRAY<STRING>`) so unlisted columns are preserved and explicit NULLs are still applied. Do NOT hand-roll a sentinel value plus a cleanup view.
- `COLUMNS TO UPDATE` and `IGNORE NULL UPDATES` are mutually exclusive; the status column must be a non-null `ARRAY<STRING>` for upsert rows
- Nested struct paths in the status column (e.g. `address.city`) are supported; a top-level struct name (e.g. `address`) updates all of its sub-fields.
