# Rust, C++, C#/.NET, and Pure C SDKs

Read this when the producer is in **Rust, C++, .NET, or pure C**. For Python, TypeScript, Go, or Java, use those language references instead.

Use environment variables from [authentication.md](authentication.md): `ZEROBUS_SERVER_ENDPOINT`, `DATABRICKS_WORKSPACE_URL`, `ZEROBUS_TABLE_NAME`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`.

For the non-blocking pattern (queue, use ack callbacks where available, `flush()` at the boundary, `close()` at shutdown), see [SKILL.md#step-4-build-the-producer](../SKILL.md#step-4-build-the-producer).

Record formats per SDK (JSON, Protobuf, Avro, Arrow Flight) and the examples folders are in [SKILL.md](../SKILL.md#sdks-record-formats-and-working-examples).

## Rust

**Callbacks:** Yes | **Install:** `cargo add databricks-zerobus-ingest-sdk`

Pure SDK; compiles from source into your binary. Fully async with `tokio` runtime. Pass an `AckCallback` implementation to `.ack_callback(...)` for progress; it runs in a dedicated task. Arrow Flight doesn't support callbacks. Payloads are under 10 MiB per ingest call (configurable). Check `e.is_retryable()` on errors; the SDK recovers retryable ones automatically.

Read the [Rust SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md) for the builder API and examples.

## C++

**Callbacks:** Yes | **Install:** from [GitHub release bundle](https://github.com/databricks/zerobus-sdk/releases) (prebuilt FFI for Linux glibc/musl and Windows) or build from source ([build-from-source.md](build-from-source.md))

C++17 compiler, CMake 3.16+. Register an `AckCallback` with lambdas (`onAck` and `onError`; both must be `noexcept`) for progress. Supports Protobuf without a `.proto` file via `ProtoSchema::from_uc_json()`. Build from source on macOS.

Read the [C++ SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/cpp/README.md) for installation and API details.

## C#/.NET

**Callbacks:** No | **Install:** `dotnet add package Databricks.Zerobus.Ingest.Sdk` (includes Linux glibc/musl and Windows binaries; macOS is source-build only)

.NET 8+. Ingest calls queue and return; call `Flush()` at a boundary or on an interval for progress. No ack callback documented. `WaitForOffset(offset)` is advanced: use it only when code must not proceed until one record is durable. Use `CreateJsonStream` for JSON, `CreateProtoStream` for Protobuf. `ZerobusException` has `IsRetryable`; retryable errors are recovered by the SDK.

Read the [.NET SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/dotnet/README.md) for API details and examples.

## Pure C (`purec`)

**Doesn't send data yet** | **Callbacks:** No

C99, CMake 3.13+, no dependencies beyond pthreads. Per the repo's own example, the SDK validates inputs and returns statuses but **performs no network I/O yet**. Don't use it to deliver data until it ships. Use C++ from source, Rust, or [REST](rest.md) instead. Check the latest commits at [github.com/databricks/zerobus-sdk/tree/main/purec](https://github.com/databricks/zerobus-sdk/tree/main/purec).

## Sources

- [Rust SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md) and [examples](https://github.com/databricks/zerobus-sdk/tree/main/rust/examples)
- [C++ SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/cpp/README.md) and [examples](https://github.com/databricks/zerobus-sdk/tree/main/cpp/examples)
- [.NET SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/dotnet/README.md) and [examples](https://github.com/databricks/zerobus-sdk/tree/main/dotnet/examples)
