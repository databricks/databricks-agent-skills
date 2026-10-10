# Protobuf Schema Management

Read this when the producer will send **Protobuf** (recommended for production): to generate a `.proto` from the target table, compile it, map Delta types, and pass the descriptor to the SDK.

**When to use:** Production workloads, high-throughput ingestion, type safety, and smaller payloads. For prototyping, use JSON instead.

Zerobus uses **proto2** syntax. Declare a field `optional` when its Delta column is nullable.

## Step 1: Generate the `.proto` from a table

Prerequisites: table exists, service principal credentials, workspace URL, and the SDK installed (`pip install databricks-zerobus-ingest-sdk`).

```bash
python -m zerobus.tools.generate_proto \
  --uc-endpoint "https://<workspace-url>" \
  --client-id "$DATABRICKS_CLIENT_ID" \
  --client-secret "$DATABRICKS_CLIENT_SECRET" \
  --table "main.iot.readings" \
  --output "my_events.proto" \
  --proto-msg "MyEvent"
```

**Java:** `java -jar zerobus-ingest-sdk-<version>-jar-with-dependencies.jar --uc-endpoint ... --table ... --output my_events.proto`.

**Verify:** `my_events.proto` exists. **Expected:** a proto2 file:

```protobuf
syntax = "proto2";

message MyEvent {
  optional string device_name = 1;
  optional int32 temp = 2;
  optional int64 humidity = 3;
  optional int64 event_time = 4;  // TIMESTAMP: microseconds since the Unix epoch
}
```

The generator writes only the `.proto`. Compile it in Step 2.

## Step 2: Compile the `.proto`

Use `protoc` for Go, Java, or C++: `protoc --go_out=. --go_opt=paths=source_relative my_events.proto` (Go); `protoc --java_out=<dir> my_events.proto` (Java); `protoc --cpp_out=. my_events.proto` (C++).

**Python:** `python -m grpc_tools.protoc -I. --python_out=. my_events.proto`

**TypeScript:** `npm install --save-dev protobufjs-cli` then `npx pbjs -t static-module -w commonjs -o my_events_pb.js my_events.proto`

**Rust:** add `prost` and `prost-types` to `Cargo.toml`, then in `build.rs`: `prost_build::compile_protos(&["my_events.proto"], &["."])?`

See the SDK READMEs for language-specific details.

## Type mappings: Delta to Protobuf (proto2)

From the SDK's type table. Declare fields `optional` when the Delta column is nullable.

| Delta type | Protobuf type | Example | Note |
|------------|---------------|---------|------|
| `TINYINT` / `BYTE`, `SMALLINT` / `SHORT`, `INT` | `int32` | `optional int32 temp = 2;` | |
| `BIGINT` / `LONG` | `int64` | `optional int64 event_count = 3;` | |
| `FLOAT` | `float` | `optional float latitude = 4;` | |
| `DOUBLE` | `double` | `optional double longitude = 5;` | |
| `STRING` / `VARCHAR` | `string` | `optional string device_name = 1;` | |
| `BOOLEAN` | `bool` | `optional bool is_active = 6;` | |
| `BINARY` | `bytes` | `optional bytes payload = 7;` | |
| `DECIMAL` | `string` | `optional string price = 8;` | **Encoded as text**, for example `"19.99"` |
| `DATE` | `int32` | `optional int32 event_date = 9;` | Days since the Unix epoch |
| `TIMESTAMP` | `int64` | `optional int64 event_time = 10;` | Microseconds since the Unix epoch |
| `TIMESTAMP_NTZ` | `int64` | `optional int64 local_time = 11;` | Microseconds since the Unix epoch |
| `ARRAY<type>` | `repeated` type | `repeated string tags = 12;` | |
| `MAP<key, value>` | `map<key, value>` | `map<string, string> metadata = 13;` | |
| `STRUCT<fields>` | nested message | `optional Location location = 14;` | |
| `VARIANT` | `string` | `optional string attributes = 15;` | A JSON-encoded string |

**Important:** TIMESTAMP columns expect **epoch microseconds** (integer), not ISO 8601 strings.

Proto schema rules: a message must contain at least every non-nullable column; at most **2000 columns** per schema; table and column names use **ASCII letters, digits, and underscores** only ([schema-management.md](schema-management.md)).

**Important:** TIMESTAMP fields must be epoch microseconds (integer), not ISO 8601 strings. DECIMAL must be encoded as a text string, for example `"19.99"`.

For ingestion examples in your language, see the SDK reference files (python-sdk.md, java-sdk.md, go-sdk.md, etc.). Pass the compiled descriptor to the `TableProperties` or table builder; the SDK validates and encodes records.

## Sources

- [Zerobus schema management](https://docs.databricks.com/ingestion/zerobus-schema-management) (proto schema rules)
- [Zerobus SDKs README: Delta type mappings](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/README.md)
- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md) (`zerobus.tools.generate_proto`, proto2, `TableProperties` descriptor)
- [Java SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md) (`GenerateProto` tool)
- [protobufjs-cli](https://www.npmjs.com/package/protobufjs-cli)
