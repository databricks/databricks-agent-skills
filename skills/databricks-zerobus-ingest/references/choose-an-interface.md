# Choose a Zerobus interface

Read this before writing code when the source might not need an SDK, when the runtime is unusual (edge, serverless, minimal container), or when you're unsure Zerobus is the right tool at all.

## Step 1: Should you recommend Zerobus?

**Recommend** when: data is **pushed** (app, device, service); destination is **Databricks / Delta**; workload is **continuous or event-driven** (latency ~5 seconds OK); **one primary consumer** (lakehouse) or **message bus as pipe** to it; no broker wanted.

**Don't recommend:** many consumers outside Databricks → **message bus** (Kafka, Kinesis); data already in Kafka, pull into lakehouse → **managed Kafka connector** (Lakeflow Connect Beta) or **Spark Structured Streaming**.

**Zerobus fits when:**
- Batches via **Arrow Flight** (columnar) instead of **Auto Loader** (files in storage)
- SaaS app can **push** (REST, OTLP, Kafka-compat, MQTT) instead of **Lakeflow Connect** (pull)
- **Debezium Server Zerobus sink** (CDC) instead of **Lakeflow Connect** (DB connectors)

## Step 2: Does the source already speak a supported protocol or tool?

**Prefer off-the-shelf over custom code.** The Kafka-compatible APIs, MQTT, and Arrow Flight are bundled in this skill.

| Source | Use | Status |
|--------|-----|--------|
| **OpenTelemetry** | OTLP endpoint | GA |
| **Kafka producer** | Kafka-compatible APIs (write-only) | Beta |
| **MQTT v5** devices | MQTT endpoint (JSON, QoS 0/1) | Beta |
| **Debezium CDC** | Debezium Server Zerobus sink (3.7+) | Debezium docs |
| **Vector** | `databricks_zerobus` sink | Vector docs |
| **Telegraf** | `outputs.zerobus` plugin (1.40+) | Telegraf docs |
| **Cribl Stream** | Databricks Zerobus destination | Cribl docs |
| **Columnar batches** (Parquet, Arrow, DataFrames) | Arrow Flight (Python, Rust, Java, Go cgo, C++, TypeScript; [per SDK](../SKILL.md#sdks-record-formats-and-working-examples)) | GA |

If none fit, continue to Step 3.

## Step 3: SDK or REST? Check the runtime first

Ask two questions: **"Where does the producer run?"** and **"Can that environment use precompiled binaries or native libraries?"** If the user doesn't know, **assume precompiled binaries are allowed** and start with the wrapper SDK for their language. Change course only if you hit a problem that shows they aren't: for example, no wheel or prebuilt package for the platform, a native library that fails to load, or cgo disabled. Then pick a path from the table below.

There are two kinds of SDK:
- **Pure SDKs: Rust, pure Go (`purego/`), and pure C (`purec/`).** They have **no precompiled binaries**. Rust compiles from source with cargo. Pure Go "speaks gRPC directly and links no Rust FFI, so it needs no cgo and no prebuilt native libraries." Pure C is C99 with only pthreads.
- **Wrapper SDKs: Python, TypeScript, Java, Go (`go/`, cgo), C++, and C#/.NET.** They load or link a **prebuilt Rust core** (wheels, NAPI prebuilds, JNI libraries, a static library in tagged Go releases, an FFI bundle). When no prebuilt binary exists for the platform (for example Alpine for Python, TypeScript, or CGO Go, or glibc older than 2.34 for Python), you can **build the SDK from source** with a Rust toolchain: [build-from-source.md](build-from-source.md).

| Producer environment | Use | Read |
|----------------------|-----|------|
| Long-running service, worker, or script where prebuilt native libraries are fine | **A gRPC SDK** in the producer's language: highest throughput, per-stream ordering, built-in recovery | [python-sdk.md](python-sdk.md), [typescript-sdk.md](typescript-sdk.md), [go-sdk.md](go-sdk.md), [java-sdk.md](java-sdk.md), [other-sdks.md](other-sdks.md) |
| **No prebuilt binary for the platform**, but compiling is allowed: Alpine or other musl Linux, glibc older than 2.34 (Python), an uncommon CPU, FreeBSD | **Build the wrapper SDK from source** with a Rust toolchain. Java, .NET, and C++ already ship musl binaries, so on Alpine only Python, TypeScript, and CGO Go need a build | [build-from-source.md](build-from-source.md) |
| **Precompiled binaries aren't allowed**: security policy, air-gapped or source-only builds, unsupported OS or CPU, cgo disabled, fully static binaries | **A pure SDK**: **Rust**, or **pure Go** (`purego`, Go 1.25+). If the policy allows compiling it yourself, a source build of the wrapper SDK also works ([build-from-source.md](build-from-source.md)). **Pure C** is the C/C++ option, but it does **no network I/O yet**, so don't use it to deliver data today (see below) | [other-sdks.md](other-sdks.md), [go-sdk.md](go-sdk.md) |
| C or C++ producer where precompiled binaries aren't allowed | Until pure C ships: **build the C++ SDK's Rust FFI from source** (needs a Rust toolchain), call the **Rust SDK**, or use **REST** | [build-from-source.md](build-from-source.md#c), [other-sdks.md](other-sdks.md), [rest.md](rest.md) |
| **Edge or serverless runtime** that can't load native code or hold a connection (Cloudflare Workers, Deno Deploy, similar) | **REST API** (GA), with token refresh | [rest.md](rest.md) |
| Language without an SDK, or occasional low-volume sends | **REST API** | [rest.md](rest.md) |
| Building a **custom client from scratch** (no SDK fits, and the producer needs streaming throughput and durability acks that REST doesn't give) | **The Zerobus gRPC API** directly, generating stubs from the SDK's `.proto` and modeling the client on the SDKs | [grpc-api.md](grpc-api.md) |

## SDK runtime compatibility

| SDK | Pure? | Language | Precompiled binary? | Edge runtimes | When to use |
|-----|-------|----------|---------------------|---------------|-------------|
| **Rust** | Yes | 1.70+ | No; compile with cargo | No | Pure, high perf |
| **Go** (`purego/`) | Yes | 1.25+ | No; pure Go, gRPC direct | Not documented | No cgo, no prebuilt libs |
| **Pure C** (`purec/`) | Yes | C99 | No; pthreads only | n/a | Doesn't send data yet (no network I/O) |
| **Python** | No | 3.9 to 3.14 | Yes (Linux glibc 2.34+, macOS, Windows). Alpine: [build from source](build-from-source.md#python) | No | Databricks classic/serverless, sync + async |
| **TypeScript** | No | Node 16+ | Yes (Linux glibc, macOS, Windows). Alpine: [build from source](build-from-source.md#typescript-nodejs) | **No** (use REST) | Long-running Node only |
| **Go** (`go/`) | No | 1.21+ | Yes (cgo, glibc Linux, macOS, Windows). Alpine: use `purego` | No | Needs cgo |
| **Java** | No | 8+ | Yes (Linux musl+glibc, Windows). macOS: [build from source](build-from-source.md#java) | No | |
| **C++** | No | C++17 | Yes (Linux musl+glibc, macOS, Windows) | No | |
| **.NET** | No | 8+ | Yes (Linux musl+glibc, Windows). macOS: [build from source](build-from-source.md#net) | No | |

**Ask if precompiled binaries are allowed.** If `pip install` downloads `.tar.gz` and fails building, no wheel matches the platform ([build-from-source.md](build-from-source.md)).

## Sources
- [Zerobus API protocols](https://docs.databricks.com/ingestion/zerobus-api-protocols)
- [Zerobus overview](https://docs.databricks.com/ingestion/zerobus-overview)
- SDK READMEs: [python](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md), [typescript](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/typescript/README.md), [go](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md), [purego](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/purego/README.md), [java](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md), [rust](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md), [cpp](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/cpp/README.md), [dotnet](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/dotnet/README.md)
- Tool docs linked in the Step 2 table
