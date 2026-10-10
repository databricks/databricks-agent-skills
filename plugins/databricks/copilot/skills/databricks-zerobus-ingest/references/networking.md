# Networking

Read this when the producer can't connect, runs **on-premises** or behind a **corporate proxy or firewall**, needs **private connectivity**, sits in another region, or when table storage is firewalled. Content comes from the Zerobus networking deep dive, the SDK README, and the API docs, so you don't need to fetch them.

## Two network legs
"Zerobus Ingest always runs in the region of your workspace." A write crosses two legs, and you secure them differently:

| Leg | Path | How to secure it |
|-----|------|------------------|
| **1. Producer → Zerobus** | Your producer connects to the **regional endpoint** | Public internet over TLS by default; **front-end PrivateLink** for supported interfaces |
| **2. Zerobus → your table's storage** | Zerobus writes from **Databricks serverless compute** | If storage is firewalled, **allowlist the serverless outbound IPs** |

## Leg 1: ports, TLS, and private connectivity per interface
| Interface | Port | Encryption | PrivateLink |
|-----------|------|------------|-------------|
| gRPC SDKs, REST, OTLP, Arrow | 443 | TLS/HTTPS | Yes |
| Apache Kafka-compatible producer APIs | 9092 | SASL_SSL | **No**: public endpoint only |
| MQTT v5 | 8883 | TLS | **No**: public endpoint only |

All need outbound **HTTPS (443)** to workspace URL (for OAuth tokens).

**Endpoints:** `<workspace-id>.zerobus.<region>.cloud.databricks.com` (AWS), `.azuredatabricks.net` (Azure), `.gcp.databricks.com` (GCP). Details in [authentication.md](authentication.md).

### Front-end PrivateLink
Use when traffic must stay private, or for predictable bandwidth. Zerobus uses the **same workspace front-end private connectivity** as the rest of your workspace (AWS PrivateLink, Azure Private Link, GCP Private Service Connect). Point the producer at the normal endpoint from inside the network. MQTT and Kafka can't use it; move to SDK, REST, or OTLP for private paths.

## On-premises producers
On-prem reach the same regional endpoint. **Allow egress** on **443** (+ **8883** for MQTT, **9092** for Kafka). For **HTTP proxy**, set environment variables (SDKs tunnel through; see above). For **private traffic**, use front-end PrivateLink over your existing on-prem private connection (AWS Direct Connect, Azure ExpressRoute, Google Cloud Interconnect); configure on-prem DNS to resolve the endpoint to the private address. Not available for MQTT or Kafka. **Far from the workspace region?** Expect latency and cross-region egress; measure with a POC.

### HTTP proxy support (SDKs only)
**SDKs' gRPC connections only.** Not documented for Kafka or MQTT; allow direct egress or use REST through the proxy.

Set environment variables (checked in order): `grpc_proxy` / `GRPC_PROXY`, `https_proxy` / `HTTPS_PROXY`, `http_proxy` / `HTTP_PROXY`. Also set `no_proxy` / `NO_PROXY` to bypass for specific hosts:
```bash
export https_proxy=http://my-proxy:8080
export no_proxy=localhost,127.0.0.1
```
SDK establishes a plaintext HTTP CONNECT tunnel (proxy never sees decrypted traffic) then TLS handshakes with Databricks. Proxy must allow `CONNECT` on 443. TLS-inspecting proxies aren't documented; confirm first.

## Leg 2: firewalled table storage
"Zerobus Ingest makes your data durable and then writes it into your target table's storage from Databricks serverless compute." If the storage account or bucket restricts inbound traffic, **allowlist the Databricks serverless outbound IP ranges** for the workspace's cloud and region. They're published at `https://www.databricks.com/networking/v1/ip-ranges.json` (and in the Databricks network reference, "Outbound IPs for serverless compute"). Symptom when this is missing: producers get acks, but rows never appear in the table.

## Cross-region
Keep producers in the workspace's region when possible. Cross-region adds latency and egress charges. Measure with a POC rather than quoting costs (varies by cloud, region, volume).

## Compression and bytes on the wire
| Interface | Option |
|-----------|--------|
| Arrow Flight | IPC compression: `ZSTD` (best ratio) or `LZ4_FRAME` (CPU-constrained clients) |
| OTLP | gzip on all services |
| Kafka-compatible | **None**: compressed batches are rejected |
| All SDKs | Prefer **Protobuf or Arrow over JSON** to send fewer bytes |

## Verify connectivity
From the producer host:
```bash
openssl s_client -connect <endpoint>:443 -brief </dev/null      # gRPC, REST, OTLP, Arrow
curl -s -o /dev/null -w "%{http_code}\n" https://<url>/oidc/v1/token  # token
openssl s_client -connect <endpoint>:9092 -brief </dev/null     # Kafka
openssl s_client -connect <endpoint>:8883 -brief </dev/null     # MQTT
```
**Expected:** `CONNECTION ESTABLISHED` on each; token endpoint returns HTTP status. Behind proxy, set proxy env vars.

## Common issues
| Symptom | Cause | Fix |
|---------|-------|-----|
| Connection timeout | Egress blocked on 443 / 8883 / 9092, or the wrong region in the endpoint | Open egress to the endpoint and workspace URL; check the endpoint format |
| Works on a laptop, fails in the data center | Corporate proxy or firewall | Set `https_proxy` / `grpc_proxy`; allow `CONNECT` to the endpoint on 443 |
| DNS resolution fails | Wrong domain for the cloud, or private DNS not configured for PrivateLink | Use the right domain (`.cloud.databricks.com`, `.azuredatabricks.net`, `.gcp.databricks.com`); fix private DNS |
| MQTT or Kafka fails on a private-only network | No front-end PrivateLink for those interfaces | Use the public endpoint, or move to an SDK, REST, or OTLP |
| Acks arrive but no rows appear | Storage firewall blocks serverless outbound IPs | Allowlist the serverless IP ranges for the region |
| Low throughput from far away | Cross-region latency | Run producers in the workspace's region |

## Sources
- [Zerobus networking deep dive](https://docs.databricks.com/ingestion/zerobus-networking)
- [Zerobus SDK README: HTTP proxy support](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/README.md)
- [Zerobus API protocols](https://docs.databricks.com/ingestion/zerobus-api-protocols), [Kafka-compatible APIs](https://docs.databricks.com/ingestion/zerobus-kafka)
- [Databricks serverless outbound IP ranges](https://www.databricks.com/networking/v1/ip-ranges.json)
