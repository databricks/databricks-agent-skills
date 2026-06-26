# Ingestion decision tree

Databricks ships several first-party ingestion approaches and the right pick depends on **where the data lives** and **whether you need a copy in your lakehouse**. This reference is the map for choosing between them.

The four approaches:

- **Lakeflow Connect** — managed pull for SaaS apps and databases. Fastest path when a connector for your source exists.
- **Auto Loader** — code-yours pull for files on cloud object storage. Full control, file sources only.
- **Lakehouse Federation** — query-in-place; the data stays in the source.
- **Delta Sharing** — the inbound side of someone else's lakehouse; you accept a share rather than build a pipeline.

For event-driven push (the source pushes to you instead of you pulling) the relevant approach is **Zerobus Ingest**, covered separately in the **databricks-zerobus-ingest** skill.

---

## Decision table

Pick the row that matches your source type and constraint.

| Where does the data live? | Need a copy? | Approach | Read more |
|---|---|---|---|
| SaaS app with a Lakeflow Connect connector (Salesforce, Workday, ServiceNow, GA4, HubSpot, Confluence, etc.) | Yes | Lakeflow Connect | [SKILL.md](../SKILL.md), [1-saas-connectors.md](1-saas-connectors.md) |
| Operational database (SQL Server, PostgreSQL, MySQL) with a Lakeflow Connect connector | Yes, with CDC | Lakeflow Connect | [2-database-connectors.md](2-database-connectors.md) |
| Operational database, low query volume, source can absorb the load | No copy needed | Lakehouse Federation | [docs](https://docs.databricks.com/aws/en/query-federation/) |
| Cloud object storage (S3, ADLS, GCS) with files | Yes | Auto Loader | **databricks-pipelines** |
| SaaS file repo (SharePoint, Google Drive, SFTP) | Yes | Lakeflow Connect | [public connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) |
| Application or device pushing events at you | Yes (push, not pull) | Zerobus Ingest | **databricks-zerobus-ingest** |
| Another lakehouse / partner data product offering a Delta share | Yes (accept, not build) | Delta Sharing | [docs](https://docs.databricks.com/aws/en/delta-sharing/) |
| None of the above | — | Hand-rolled Structured Streaming or `read_files` from object storage | **databricks-spark-structured-streaming** |

---

## Lakeflow Connect vs Auto Loader

Both pull data into Delta tables, but they cover different source types.

**Lakeflow Connect wins when:**
- The source is a SaaS application or a database (not files on object storage).
- The source has its own auth (OAuth, API key, DB user).
- You want CDC, schema evolution, and retries handled by the platform.
- You prefer declarative configuration over code.

**Auto Loader wins when:**
- The source is files on cloud object storage (S3, ADLS, GCS).
- You need custom file format parsing or inline transforms.
- You want full control over checkpointing, schema hints, and trigger cadence.

**Common confusion**: SFTP and SharePoint look like file sources but go through Lakeflow Connect, not Auto Loader. Auto Loader is for **cloud object storage** specifically.

---

## Lakeflow Connect vs Lakehouse Federation

Both let you work with data that lives outside your lakehouse, but the difference is whether the data gets copied.

**Lakeflow Connect wins when:**
- You need a governed Delta copy in your lakehouse for performance, ML training, or downstream pipelines.
- Query volume against the source data is high.
- The source is performance-sensitive (you don't want to add query load to your production OLTP).
- You need point-in-time history (CDC applied into a Delta table with `APPLY CHANGES` / AUTO CDC semantics).

**Lakehouse Federation wins when:**
- Data should stay in the source for governance or residency reasons.
- Query patterns are sparse (a few analysts, occasional ad-hoc queries).
- The source can comfortably absorb additional query load.
- You don't need history beyond what the source already retains.

**Common confusion**: both use a Unity Catalog `CONNECTION` object. The difference is what you do with it — Lakeflow Connect creates an ingestion pipeline that materializes to Delta; Federation creates a foreign catalog that queries through to the source.

---

## Lakeflow Connect vs Delta Sharing

Delta Sharing is not really a build decision; it's the receiving end of someone else's pipeline.

**Lakeflow Connect**: you build the ingestion pipeline. You own the connector configuration, the schedule, and the destination tables. Source can be anything LFC supports.

**Delta Sharing**: a data provider (another lakehouse, a partner product) offers you a share. You accept it via a Delta Sharing client and the data appears in your catalog as a shared table. You don't operate the pipeline.

Use Delta Sharing when a data partner offers it — there's nothing to build. Use Lakeflow Connect when you need to pull from a system the partner doesn't share to.

---

## Lakeflow Connect vs Zerobus Ingest

The push-vs-pull distinction.

**Lakeflow Connect** is **pull-based**: the ingestion pipeline reaches out to the source on a schedule.

**Zerobus Ingest** is **push-based**: an application or device pushes records into a Delta table via gRPC. There is no source system to pull from — the producer drives the cadence.

Use Lakeflow Connect when the source is a system you query. Use Zerobus when the source is an application you control (or a device emitting events) that wants to write directly.

---

## Cost considerations

All four approaches are billed in DBUs (compute time), with no per-row or per-connector fee.

- **Lakeflow Connect**: serverless ingestion pipeline DBUs; database connectors also incur classic-compute gateway DBUs.
- **Auto Loader**: serverless or classic compute DBUs depending on where the pipeline runs.
- **Lakehouse Federation**: SQL warehouse DBUs for the queries that read through the foreign catalog. Plus any costs the source charges.
- **Delta Sharing**: typically free for the recipient (the provider may charge separately outside Databricks).
- **Zerobus Ingest**: per-GB ingested, billed under the Lakeflow Jobs Serverless SKU.

See the [Databricks pricing page](https://www.databricks.com/product/pricing) and the per-product pricing pages linked from there.

---

## When Lakeflow Connect doesn't fit yet

A few situations where you'll reach for one of the alternatives:

- **The connector for your source isn't in the catalog.** Check the [connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) — if your source isn't listed, use Auto Loader (if it's files), a hand-rolled Structured Streaming job, or wait for the connector to ship.
- **You need continuous ingestion.** Lakeflow Connect runs triggered only (no continuous mode). For sub-minute latency on file sources, use Auto Loader with `Trigger.AvailableNow` on a short interval, or Structured Streaming directly.
- **You need to push instead of pull.** That's Zerobus.
- **You want zero copy.** That's Lakehouse Federation.

---

## Resources

- [Lakeflow Connect overview](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect)
- [Connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors)
- [Auto Loader docs](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/)
- [Lakehouse Federation docs](https://docs.databricks.com/aws/en/query-federation/)
- [Delta Sharing docs](https://docs.databricks.com/aws/en/delta-sharing/)
- [Pricing](https://www.databricks.com/product/pricing)
