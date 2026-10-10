# TypeScript SDK

Read this when the producer is **Node.js** (TypeScript or JavaScript). The SDK loads a native library, so edge runtimes need [REST](rest.md) instead.

**Record formats:** JSON, Protobuf, and Arrow Flight ([SKILL.md](../SKILL.md#sdks-record-formats-and-working-examples)).

**Runtime Requirements:**
- Node.js 16 or higher
- NAPI prebuilds (required): Linux glibc x64 and arm64, macOS x64 and arm64, Windows x64. No prebuilt for Alpine or Windows arm64; use [build-from-source.md](build-from-source.md#typescript-nodejs) or REST for edge runtimes
- **Process model:** long-lived stream with acks tracked in the background

For the non-blocking pattern (queue with `ingestRecordOffset`, `flush()` at the boundary, `close()` at shutdown), see [SKILL.md#step-4-build-the-producer](../SKILL.md#step-4-build-the-producer). TypeScript does not document an ack callback; call `flush()` on an interval for progress.

## Installation

```bash
npm install @databricks/zerobus-ingest-sdk
```

## JSON Example

```typescript
import { ZerobusSdk, RecordType } from '@databricks/zerobus-ingest-sdk';

const sdk = new ZerobusSdk(process.env.ZEROBUS_SERVER_ENDPOINT!, process.env.DATABRICKS_WORKSPACE_URL!);
const stream = await sdk.createStream(
    { tableName: process.env.ZEROBUS_TABLE_NAME! },
    process.env.DATABRICKS_CLIENT_ID!,
    process.env.DATABRICKS_CLIENT_SECRET!,
    { recordType: RecordType.Json }, // the default is Protobuf
);

try {
    for (let i = 0; i < 100; i++) {
        // Resolves when the record is queued, not when it's acknowledged
        await stream.ingestRecordOffset({ device_name: `sensor-${i % 10}`, temp: 20 + (i % 15) });
    }
    await stream.flush(); // durability boundary
} finally {
    await stream.close();
}
```

**Verify:** runs without errors. **Expected:** records land in the target table.

## Protobuf

For type safety, set `recordType: RecordType.Proto` and pass `descriptorProto` bytes. The `RecordType` enum has `Json`, `Proto`, and `Avro` (not `Protobuf`). Use `loadDescriptorProto(...)` to load descriptor bytes from a file. The SDK uses protobufjs static modules with camelCase field names. See the working example at [`typescript/examples/proto/single.ts`](https://github.com/databricks/zerobus-sdk/blob/main/typescript/examples/proto/single.ts) and [protobuf-schema.md](protobuf-schema.md).

**Edge runtimes:** The SDK uses native binaries and doesn't work on Cloudflare Workers, Deno Deploy, AWS Lambda, or other platforms that forbid them. Use [REST](rest.md) instead.

For the full API and more examples, read the [TypeScript SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/typescript/README.md).

## Sources

- [TypeScript SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/typescript/README.md)
- [TypeScript SDK examples](https://github.com/databricks/zerobus-sdk/tree/main/typescript/examples)
