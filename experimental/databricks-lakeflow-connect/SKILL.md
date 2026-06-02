---
name: databricks-lakeflow-connect
description: "Build managed ingestion pipelines into Databricks using Lakeflow Connect. Use when ingesting from SaaS apps (Salesforce, Workday Reports, ServiceNow, Google Analytics 4, HubSpot, Confluence), databases (SQL Server cloud and on-prem; PostgreSQL/MySQL CDC in PuPr), or file sources (SharePoint, Google Drive, SFTP) into Unity Catalog with serverless pipelines. Covers the unified setup pattern (UC connection -> ingestion pipeline -> streaming Delta tables), the gateway pattern for database CDC, DAB-based authoring, and the decision between Lakeflow Connect, Auto Loader, Lakehouse Federation, and Delta Sharing."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Lakeflow Connect

Build managed ingestion pipelines that pull from SaaS apps and databases into Unity Catalog Delta tables, governed end-to-end and powered by serverless Lakeflow Spark Declarative Pipelines.

**Status:** mixed catalog — GA connectors for production use, plus Public Preview, Beta, and Private Preview connectors that expand over time. See the connector catalog below.

---

## What Is Lakeflow Connect?

Managed connectors for ingesting data from SaaS applications and databases. The resulting ingestion pipeline is governed by Unity Catalog and powered by serverless compute and Lakeflow Spark Declarative Pipelines.

Three frames to keep in mind:

- **Simple and low-maintenance** — no client code to write, no message bus to operate; connector + UC Connection + a serverless pipeline.
- **Unified with the lakehouse** — credentials stored in UC, output is governed Delta, runs on Jobs and SDP like any other workload.
- **Efficient incremental processing** — change tracking / CDC / schema evolution / retries are built in.

There are four architecture patterns:

1. **SaaS pull** — connector reads from an external SaaS via OAuth or API key, lands in a streaming Delta table.
2. **Database CDC via gateway** — an ingestion gateway runs in the customer's network, stages change events to a UC Volume, a serverless ingestion pipeline applies them as CDC into Delta.
3. **Query-based** — for sources without native CDC (Oracle / Teradata / SQL Server / PG / MySQL query-based, Snowflake / Redshift / Synapse / BigQuery via Foreign Catalog), the connector issues periodic queries instead of subscribing to a change feed.
4. **Community connectors** — template-based, out of scope for this skill.

---

## Connector catalog

Lakeflow Connect ships connectors at multiple release stages. **GA** and **Public Preview** connectors are production-supported; **Beta** and **Private Preview** are early-access and not production-supported.

### GA connectors

Full coverage in this skill.

| Source | Type | Auth | Reference |
|--------|------|------|-----------|
| Salesforce (Sales / Service / etc.) | SaaS pull | OAuth U2M | [1-saas-connectors.md](references/1-saas-connectors.md) |
| Workday Reports (RaaS) | SaaS pull | OAuth refresh token / basic | [1-saas-connectors.md](references/1-saas-connectors.md) |
| ServiceNow | SaaS pull | OAuth U2M / basic | [1-saas-connectors.md](references/1-saas-connectors.md) |
| Google Analytics 4 | SaaS pull (via BigQuery) | Service-account JSON | [1-saas-connectors.md](references/1-saas-connectors.md) |
| HubSpot | SaaS pull | OAuth | [1-saas-connectors.md](references/1-saas-connectors.md) |
| Confluence | SaaS pull | OAuth | [1-saas-connectors.md](references/1-saas-connectors.md) |
| SQL Server (cloud) | Database CDC | DB user + change tracking / CDC | [2-database-connectors.md](references/2-database-connectors.md) |
| SQL Server (on-prem) | Database CDC | DB user + ExpressRoute / Direct Connect | [2-database-connectors.md](references/2-database-connectors.md) |

### Public Preview connectors

Production-supported. Configuration may evolve before GA. Deep coverage is being added incrementally; until then, see the [public connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) for current setup steps.

| Source | Type | Auth |
|--------|------|------|
| NetSuite | SaaS pull | OAuth |
| Dynamics 365 | SaaS pull | OAuth |
| PostgreSQL CDC | Database CDC | DB user + gateway |
| MySQL CDC | Database CDC | DB user + gateway |
| Oracle / Teradata / SQL Server / PG / MySQL (query-based) | Database query | DB user |
| Snowflake / Redshift / Synapse / BigQuery (Foreign Catalog) | Database query | Foreign Catalog |
| SFTP | File pull | Key / password |

### Beta and Private Preview

Early-access connectors are not production-supported. The list changes month to month; check the [public connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) for current availability.

For the Lakeflow-Connect-vs-Auto-Loader-vs-Federation-vs-Delta-Sharing decision, see [4-ingestion-decision-tree.md](references/4-ingestion-decision-tree.md).

---

## Required Tools

- **Databricks CLI v1.0.0+** for `databricks pipelines create` and `databricks connections create`. Verify with `databricks --version`.
- **Databricks SDK for Python** (`databricks-sdk>=0.85.0`) if you prefer SDK over CLI.
- **Declarative Automation Bundles** if authoring as IaC (recommended for any pipeline that ships to a customer environment).

No extra connector-specific SDK is needed. Lakeflow Connect reuses the pipelines API surface — pipelines are created with an `ingestion_definition` block instead of a `libraries` block, but the API and CLI are otherwise the same.

---

## Prerequisites

Confirm before creating any pipeline:

1. **A Unity Catalog target** — catalog and schema must exist; the service principal or user creating the pipeline needs `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`, and `MODIFY` on the target schema.
2. **A UC `CONNECTION` object** with credentials for the source. SaaS OAuth U2M connections must be created via the UI (Catalog Explorer); API-key and basic-auth connections can be created via CLI / DAB.
3. **For database connectors**: network reachability between the gateway (classic compute, customer VPC) and the source database. On-prem requires ExpressRoute (Azure) or Direct Connect (AWS).
4. **For file connectors**: OAuth scope grants on the SaaS file repo (SharePoint / Google Drive).

---

## Minimal Example — Salesforce ingestion pipeline

The canonical authoring path is JSON to `databricks pipelines create --json`. (There is no SQL `CREATE TABLE … FROM CONNECTION` syntax for Lakeflow Connect — that syntax exists only for Lakehouse Federation, which is a different product.)

```bash
databricks pipelines create --json '{
  "name": "salesforce_to_uc",
  "ingestion_definition": {
    "connection_name": "my_salesforce_oauth_connection",
    "objects": [
      {"table": {"source_schema": "salesforce", "source_table": "Account",
                 "destination_catalog": "main", "destination_schema": "salesforce_raw"}},
      {"table": {"source_schema": "salesforce", "source_table": "Opportunity",
                 "destination_catalog": "main", "destination_schema": "salesforce_raw"}}
    ]
  }
}'
```

For a DAB-authored version (the production path), see [1-saas-connectors.md](references/1-saas-connectors.md).

---

## Detailed guides

| Topic | File | When to read |
|-------|------|--------------|
| SaaS connectors (Salesforce, Workday Reports, ServiceNow, GA4, HubSpot, Confluence) | [1-saas-connectors.md](references/1-saas-connectors.md) | Unified SaaS pattern, per-connector deltas, OAuth flows, DAB stubs |
| Database connectors (SQL Server cloud + on-prem) | [2-database-connectors.md](references/2-database-connectors.md) | Gateway pattern, change tracking vs CDC, network setup |
| Ingestion decision tree | [4-ingestion-decision-tree.md](references/4-ingestion-decision-tree.md) | Lakeflow Connect vs Auto Loader vs Lakehouse Federation vs Delta Sharing |
| Troubleshooting and monitoring | [5-troubleshooting-and-monitoring.md](references/5-troubleshooting-and-monitoring.md) | Event log queries, common errors, escalation pointers |

---

## Workflow

For each new ingestion pipeline:

1. **Pick the connector category** — SaaS / database / file / push — and read the matching reference file.
2. **Verify prerequisites** — UC target, source credentials, network path (for databases), region availability.
3. **Create the UC `CONNECTION`** — UI for OAuth U2M, CLI / DAB for everything else.
4. **Author the pipeline** — `databricks pipelines create --json` for one-offs, DAB YAML for anything shipping to a customer.
5. **Trigger the first run** and watch the event log; see [5-troubleshooting-and-monitoring.md](references/5-troubleshooting-and-monitoring.md) for the SQL.
6. **Schedule** via Jobs (`pipeline_task`) or `continuous: false` on the pipeline itself. Lakeflow Connect supports triggered runs only (no continuous mode).

---

## Important

- **Triggered only, no continuous mode** — pipelines run on a schedule or on-demand, never continuously. Check the connector reference for the latest status.
- **Compute-only billing** — Lakeflow Connect is billed in DBUs (no per-row fee). Database connectors also incur classic-compute gateway DBUs in addition to the serverless ingestion pipeline DBUs. See the [pricing page](https://www.databricks.com/product/pricing/lakeflow-connect) for current rates.
- **Salesforce auth is OAuth U2M only** — no machine-to-machine, no basic auth. Connection creation requires a UI walk-through.
- **Database staging retention is 30 days** by default in the UC Volume between the gateway and the ingestion pipeline.
- **Limits per pipeline** — most SaaS connectors cap at 250 tables per pipeline. Split across multiple pipelines if needed.

---

## Key Concepts

- **UC `CONNECTION` is the credential anchor** — every Lakeflow Connect pipeline points at a UC connection. The connection owns the auth; the pipeline references it by name.
- **Serverless ingestion pipeline + (optional) classic gateway** — SaaS connectors are pure serverless. Database connectors split into a customer-network gateway (classic) and a serverless ingestion pipeline (Delta-bound).
- **CDC and schema evolution are built in** — for sources that support change tracking or CDC, the connector applies changes incrementally and evolves the target schema. Data-type changes typically require a full snapshot reload.
- **Streaming Delta output** — destination tables are governed Delta tables with `applyAsChangesFrom` semantics for CDC sources. Compatible with downstream materialized views and Spark streaming.
- **OAuth U2M is UI-only** — DAB / CLI cannot bootstrap OAuth U2M connections. Plan for a one-time human step.

---

## Common Issues

For common errors and their fixes — duplicate-key violations, watermark / cursor problems, schema evolution, gateway region availability, the `channel: PREVIEW` warning, and pipelines that run but land no data — see [5-troubleshooting-and-monitoring.md](references/5-troubleshooting-and-monitoring.md), which also has the event-log queries to diagnose them.

---

## Related Skills

- **databricks-pipelines** — the SDP runtime that Lakeflow Connect pipelines run on. For Auto Loader and downstream pipeline patterns.
- **databricks-zerobus-ingest** — push-based gRPC ingestion. Sibling to Lakeflow Connect's pull-based connectors.
- **databricks-dabs** — author Lakeflow Connect pipelines as IaC.
- **databricks-unity-catalog** — managing catalogs, schemas, and the UC `CONNECTION` objects that LFC credentials live in.
- **databricks-jobs** — schedule ingestion pipelines with `pipeline_task`.

---

## Resources

- [Lakeflow Connect public docs hub](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect)
- [Connector reference (per-connector setup)](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors)
- [Pricing](https://www.databricks.com/product/pricing/lakeflow-connect)
