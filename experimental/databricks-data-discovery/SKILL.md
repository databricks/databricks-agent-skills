---
name: databricks-data-discovery
description: "Discover, explore, and query Databricks data via Genie. This skill MUST be invoked — instead of browsing catalogs/schemas/tables yourself — whenever the user asks to find or locate data ('what tables are in X', 'where does X live', 'which catalog/schema has Y'), explore or sample/profile a table, answer a natural-language question about the data, or write or generate a SQL query — for analytics, dashboards, apps, or ad-hoc questions. Routes to Genie (natural-language Q&A and query generation over all your Unity Catalog data) first, then falls back to information_schema + SQL discovery."
compatibility: Requires databricks CLI with the experimental genie command (databricks experimental genie ask)
metadata:
  version: "0.0.1"
parent: databricks-core
---

# Databricks Data Discovery

This skill **routes data work** — decide first:
- the request is about *the data* — finding it, asking questions of it, or
  generating SQL → delegate to **Genie One**:
  `databricks experimental genie ask "..."` (see Routing below).
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

```bash
# Ask a natural-language question over ALL your data
databricks experimental genie ask "How many bookings were there last week?"

# Show the SQL Genie ran (text output)
databricks experimental genie ask "Top 5 destinations by revenue" --include-sql

# Machine-readable result for parsing
databricks experimental genie ask "Top 5 destinations by revenue" --output json
# → {"status":"completed","conversation_id":"…","text":"…","tool_calls":[{"name":"execute_sql","sql":"…","title":"…"}]}

# Multi-turn: reuse a session label (any string you pick) to keep context across calls
databricks experimental genie ask -s trips "How many bookings were there last week?"
databricks experimental genie ask -s trips "Break that down by destination"
```

Genie searches across all the data you can see, runs SQL, and streams a grounded
answer — rendered with the executed SQL and, where it helps, a terminal chart. It
auto-resolves a SQL warehouse (override with `--warehouse-id`); nothing to pick or
set up.

- **Streams live**: the answer, the agent's steps, and any SQL/results appear as
  they arrive. Answers usually take ~5–30s; a stalled stream (no data for ~10 min)
  fails with a clear message, and Ctrl-C cancels cleanly.
- **Follow-ups (multi-turn)**: pass `-s <label>` (alias `--session`) with a
  session label *you* choose — any string. Reusing the same label continues that
  conversation, so a follow-up keeps context ("break that down…", "now by
  region"); a fresh label starts over. The label is mapped to the server
  conversation locally, and an expired one transparently starts a new
  conversation. No id to copy around.
- **Structured output**: `--output json` gives `{status, conversation_id, text,
  tool_calls[]}`, where `tool_calls` includes the SQL Genie executed; `--raw` dumps
  the raw event stream.
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
commands — see **[Manual Data Exploration](../databricks-core/manual-data-exploration.md)**
(keyword search via `information_schema`, `discover-schema`, and `tools query`).
Running known SQL or profiling a known table that way is perfectly fine on its own.

## Caveats

- **Genie One is Beta** and its endpoint is **undocumented / not in the SDK**: the
  command streams from the workspace "Genie One" (onechat) responses API, whose wire
  shape may still change between releases.
- **Genie/Genie One must be enabled** in the workspace and the caller needs data
  access through it; otherwise use the manual fallback.
- **Older CLI without the command**: `experimental genie ask` is new; an older CLI
  fails with `Error: unknown command "genie"`. Upgrade the Databricks CLI binary
  (see the parent `databricks-core` CLI Installation reference) — separate from
  `databricks aitools install`, which installs skills, not the CLI.
- **Requires a logged-in profile** (`databricks auth login`).

## Related Skills

- **[databricks-genie](../databricks-genie/SKILL.md)** — *author and manage* curated
  Genie configurations (create, configure, import/export) and the lower-level
  Conversation API; the authoring counterpart to this consumption skill.
- **databricks-core** (parent) — CLI auth, profiles, and the manual data exploration
  reference used as the fallback.
