---
name: databricks-data-discovery
description: "Discover, explore, and query Databricks data via Genie — the CLI equivalent of the Genie One MCP. MUST be invoked whenever the user asks to find or locate data ('what tables are in X', 'where does X live', 'which catalog/schema has Y'), explore or profile a table, answer a natural-language question about the data, or write a SQL query."
compatibility: Requires databricks CLI with the experimental genie command (databricks experimental genie ask)
metadata:
  version: "0.0.1"
parent: databricks-core
---

# Databricks Data Discovery

This skill **routes data work** — decide first:
- the request is about *the data* — finding it, asking questions of it, or
  generating SQL → delegate to **Genie One**:
  `databricks experimental genie ask -s <session-label> "..."` (see Routing below).
- writing files or anything else → use your own coding-agent tools.

Genie One just needs an authenticated CLI profile (the parent `databricks-core`
skill covers auth/profiles if you need it) — but route the data request to Genie
first; don't detour into manual catalog browsing.

## Routing — Genie vs your coding agent

**Route to Genie when the request is about the data:**
- **Finding or locating data** — "what tables are in wanderbricks?", "where does X
  live?", which catalog/schema holds something. Let Genie resolve a fuzzy or partial
  name across all your data instead of guessing or grepping catalogs yourself.
- **Questions about the data** — "how many…", "what's the average…", "which … the
  most…", trends, breakdowns.
- **Generating SQL from a question** — a first-cut query you can run, adapt, or drop
  into a file.
- **Understanding or profiling data** to inform a query, dashboard, or app.

**Route to your own coding agent (do NOT use Genie) for everything else:**
- **Writing or editing files** — a `.sql` file, notebook, dashboard, app, config.
  Genie finds the data and produces the SQL; *you* write the file.
- **Authoring jobs, pipelines, apps, or DABs** — use those product skills.
- **DDL or writes** — `CREATE` / `INSERT` / `UPDATE` / `DELETE`.
- **General programming, git, infra, and any non-data task.**

**Key principle:** data discovery, data questions, and query generation → Genie One.
Everything else → your coding agent.

## Why prefer Genie for data questions

Genie runs *inside the Databricks data plane* with governed, first-hand access to
the org's Unity Catalog metadata, metric views, and curated semantic context —
context you do **not** have when reverse-engineering schemas with ad-hoc SQL. For
data questions it is often higher-quality and more performant than doing the
discovery yourself, and it keeps improving as a managed Databricks capability.
Don't default to writing your own discovery SQL just because you can.

## How to ask Genie

Always pass a session label with `-s`, and prefer reusing the **same** one: a
follow-up can only continue a conversation if the first ask set the session label,
and reusing it lets later questions build on everything asked so far ("summarize all
of the above"). Use a fresh session label only to start a deliberately separate
session, or distinct session labels to run several in parallel.

```bash
# Always pass a session label, and reuse the SAME one so follow-ups build on each other
databricks experimental genie ask -s trips "How many bookings were there last week?"
databricks experimental genie ask -s trips "Break that down by destination"
databricks experimental genie ask -s trips "Summarize all of the above"

# --include-sql also prints the SQL Genie ran (use it to generate a query, too)
databricks experimental genie ask -s trips "Write SQL for the top 5 destinations by revenue" --include-sql

# --output json gives a parseable result
databricks experimental genie ask -s trips "Top 5 destinations by revenue" --output json
# → {"status":"completed","conversation_id":"…","text":"…","tool_calls":[{"name":"execute_sql","sql":"…","title":"…"}]}
```

Genie searches across all the data you can see, runs SQL, and streams a grounded
answer — rendered with the executed SQL and, where it helps, a terminal chart. It
auto-resolves a SQL warehouse (override with `--warehouse-id`); nothing to pick or
set up.

- **Streams live**: the answer, the agent's steps, and any SQL/results appear as
  they arrive. Answers usually take ~5–30s; a stalled stream (no data for ~10 min)
  fails with a clear message, and Ctrl-C or `kill` (SIGTERM) cancels cleanly.
- **Picking a session label**: any string works — a topic like `trips`, or `$$` for a
  per-shell session. Default to reusing one session label so follow-ups keep full
  context; use a fresh one only for a deliberately separate session. An expired
  session label just starts fresh on the next ask. No id to copy around.
- **Parallelism**: to run sessions at the same time, give each its own session label
  (`-s q1`, `-s q2`, …) — independent session labels don't interfere. Within a single
  session label keep calls sequential: send a follow-up after the previous turn
  returns, and never fire two asks at once on the *same* session label (they'd split
  into two conversations and only one mapping would survive).
- **Structured output**: `--output json` gives `{status, conversation_id, text,
  tool_calls[]}`, where `tool_calls` includes the SQL Genie executed; `--raw` dumps
  the raw event stream. Note `--output json` buffers and prints once at the end (no
  live streaming) — use it for parsing, the default text output for interactive use.
- **Generating a query**: ask Genie to "write SQL for …" and read the SQL from the
  response (it's in the answer text, and `--include-sql` also shows the query Genie
  ran to verify it — so the SQL is known-good). Genie resolves the schema and joins
  for you, so this beats hand-writing SQL against unfamiliar tables.
- **For exact/full rows**: Genie shows a preview inline; to pull the complete result
  set locally, copy its SQL (`--include-sql` or the JSON `tool_calls`) into the
  parent's `... aitools tools query "<SQL>"`.
- **A non-answer is a message, not an error**: if Genie refuses or "couldn't find
  relevant data," don't retry — use the manual fallback below.

> **Naming:** "Genie One" is the current name for this cross-data chat — formerly
> "Databricks One", then "OneChat" (the backend tool is still literally named
> `onechat`). All the same thing.

## If Genie One isn't available — manual fallback

When Genie One isn't enabled, the CLI is too old to have `experimental genie ask`,
or Genie can't cover the question, do the discovery yourself with the parent skill's
commands — see **[Manual Data Exploration](../../skills/databricks-core/manual-data-exploration.md)**
(keyword search via `information_schema`, `discover-schema`, and `tools query`).
Running known SQL or profiling a known table that way is perfectly fine on its own.

## Relationship to the Genie One MCP

Databricks also offers this capability as a managed **MCP** server — the *Genie One
MCP*. This skill delivers the **same functionality** through the Databricks CLI, with
no MCP server to configure or host. More broadly, the Databricks Agent Skills cover
the same ground as Databricks' managed MCP servers, so you don't need any MCP wired up
to use this. If you already run the Genie One MCP, use whichever you prefer — they hit
the same Genie backend.

## Related Skills

- **[databricks-genie](../databricks-genie/SKILL.md)** — build and manage **Genie
  Agents**: curated agents that let you or a group ask questions of specific data
  (create, configure, import/export).
- **databricks-core** (parent) — CLI auth, profiles, and the manual data exploration
  reference used as the fallback.
