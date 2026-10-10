# Python SDK

Read this when the producer is written in **Python**. Use the non-blocking ingestion pattern; the sync API is already non-blocking for ingest.

**Runtime Requirements:**
- Python 3.9 to 3.14
- **Native library:** prebuilt `abi3` wheels. Linux x86_64 and aarch64 use `manylinux_2_34` (glibc 2.34+; that's the platform tag on the published PyPI wheels, checked for 1.10.0); also macOS and Windows x86_64. Alpine and older glibc have no wheel; build from source ([build-from-source.md](build-from-source.md#python))
- **Databricks compute:** works on classic and serverless. On serverless, add `databricks-zerobus-ingest-sdk` to dependencies
- **Process model:** long-lived stream with in-memory buffering of unacknowledged records

For the non-blocking pattern (queue with `ingest_record_offset`, use an `AckCallback` for progress, `flush()` at the boundary, `close()` at shutdown), see [SKILL.md#step-4-build-the-producer](../SKILL.md#step-4-build-the-producer). Python has ack callbacks; the async API (`zerobus.sdk.aio`) is documented in the README.

## Installation

```bash
pip install databricks-zerobus-ingest-sdk
```

Or on Databricks serverless, add to the job or notebook environment dependencies instead of pip-installing.

## JSON Ingestion

For prototyping, use JSON. The complete sample is in [SKILL.md#step-4-build-the-producer](../SKILL.md#step-4-build-the-producer). The SDK infers JSON when you pass no descriptor to `TableProperties`.

## Protobuf Ingestion

Type-safe and more efficient. Requires a `.proto` schema ([protobuf-schema.md](protobuf-schema.md)).

```python
import os
import time
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import AckCallback, StreamConfigurationOptions, TableProperties
import my_events_pb2  # generated with protoc from the .proto (protobuf-schema.md)

class Progress(AckCallback):
    def on_ack(self, offset: int):  # runs on an SDK background thread; keep it fast
        print(f"durable through offset {offset}")

    def on_error(self, offset: int, error_message: str):
        print(f"error at offset {offset}: {error_message}")

sdk = ZerobusSdk(os.environ["ZEROBUS_SERVER_ENDPOINT"], os.environ["DATABRICKS_WORKSPACE_URL"])
stream = sdk.create_stream(
    os.environ["DATABRICKS_CLIENT_ID"],
    os.environ["DATABRICKS_CLIENT_SECRET"],
    # Pass the message descriptor (MyEvent.DESCRIPTOR), not the file descriptor; it selects Protobuf
    TableProperties(os.environ["ZEROBUS_TABLE_NAME"], my_events_pb2.MyEvent.DESCRIPTOR),
    StreamConfigurationOptions(ack_callback=Progress()),
)
try:
    for i in range(100):
        record = my_events_pb2.MyEvent(
            device_name=f"sensor-{i % 10}",
            temp=20 + (i % 15),
            event_time=int(time.time() * 1_000_000),  # TIMESTAMP: epoch microseconds
        )
        stream.ingest_record_offset(record)  # queues, returns
    stream.flush()  # durability boundary
finally:
    stream.close()
```

**Verify:** the `on_ack` lines print, then run the query in [SKILL.md Step 6](../SKILL.md#step-6-verify-the-rows-landed) about 5 seconds later. **Expected:** the row count went up by 100.

For the full API, async patterns, ack callbacks, and more examples, read the [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md).

## Sources

- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md)
- [Python SDK examples](https://github.com/databricks/zerobus-sdk/tree/main/python/examples)
