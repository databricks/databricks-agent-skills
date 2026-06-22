---
name: databricks-data-discovery
description: "Discover, explore, and query Databricks data via Genie. This skill MUST be invoked — instead of browsing catalogs/schemas/tables yourself — whenever the user asks to find or locate data ('what tables are in X', 'where does X live', 'which catalog/schema has Y'), explore or sample/profile a table, answer a natural-language question about the data, or write or generate a SQL query — for analytics, dashboards, apps, or ad-hoc questions. Routes to Genie (natural-language Q&A and query generation over all your Unity Catalog data) first, then falls back to information_schema + SQL discovery."
compatibility: Requires databricks CLI with experimental aitools (the tools genie subcommand)
metadata:
  version: "0.0.1"
parent: databricks-core
---

# Databricks Data Discovery

This skill **routes data work** — decide first:
- the request is about *the data* — finding it, asking questions of it, or
  generating SQL → delegate to **Genie One**:
  `databricks experimental aitools tools genie "..."` (see Routing below).
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
databricks experimental aitools tools genie "How many bookings were there last week?"

# Machine-readable result for parsing
databricks experimental aitools tools genie "Top 5 destinations by revenue" --output json
# → {"conversation_id":"…","response_id":"…","status":"completed","answer":"…(includes a SQL block + Explore link)…"}
```

Genie searches across all the data you can see, writes SQL, and returns a grounded
answer with an "Explore in Databricks" deep link — nothing to pick or set up.

- **Asynchronous**: the command blocks and polls until Genie finishes (`--timeout`,
  default 5m; `--poll-interval`, default 2s); answers usually take ~5–30s. It
  **exits non-zero** if Genie doesn't finish successfully.
- **To get rows, not just an answer**: copy the SQL from Genie's answer into
  `... tools query "<SQL>"` to pull the actual result rows locally.
- **Follow-ups**: continue a conversation with `--conversation <id>` (the
  `conversation_id` from a prior answer); omit it to start fresh.
- **A non-answer is a message, not an error**: if Genie returns a refusal or
  "couldn't find relevant data," don't retry — use the manual fallback below.

> **Naming:** "Genie One" is the current name for this cross-data chat — formerly
> "Databricks One", and "OneChat" before that. All three are the same thing.

## If Genie One isn't available — manual fallback

When Genie One isn't enabled, the CLI is too old to have `tools genie`, or Genie
can't cover the question, do the discovery yourself with the parent skill's
commands — see **[Manual Data Exploration](../databricks-core/manual-data-exploration.md)**
(keyword search via `information_schema`, `discover-schema`, and `tools query`).
Running known SQL or profiling a known table that way is perfectly fine on its own.

## Caveats

- **Genie One is Beta** and is **not in the Databricks SDK**, so the `genie` command
  reaches it as a direct JSON-RPC request; its tool surface (`genie_ask` /
  `genie_poll_response`) may still change.
- **Genie/Genie One must be enabled** in the workspace and the caller needs data
  access through it; otherwise use the manual fallback.
- **Older CLI without the command**: `tools genie` is new; an older CLI fails with
  `Error: unknown command "genie"`. Upgrade the Databricks CLI binary (see the
  parent `databricks-core` CLI Installation reference) — separate from
  `databricks aitools install`, which installs skills, not the CLI.
- **Requires a logged-in profile** (`databricks auth login`); the command sends the
  workspace routing header the endpoint needs.

## Related Skills

- **[databricks-genie](../databricks-genie/SKILL.md)** — *author and manage* curated
  Genie configurations (create, configure, import/export) and the lower-level
  Conversation API; the authoring counterpart to this consumption skill.
- **databricks-core** (parent) — CLI auth, profiles, and the manual data exploration
  reference used as the fallback.
