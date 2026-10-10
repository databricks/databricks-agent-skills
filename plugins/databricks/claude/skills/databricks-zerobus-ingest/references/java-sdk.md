# Java SDK

Read this when the producer runs on the **JVM** (Java 8+). Use the non-blocking ingestion pattern with `streamBuilder()`, and Java has an `AckCallback` for progress.

**Record formats:** JSON, Protobuf, and Arrow Flight ([SKILL.md](../SKILL.md#sdks-record-formats-and-working-examples)).

**Runtime Requirements:**
- Java 8 or higher to run, JDK 11+ to build from source
- JNI bindings to Rust; platforms: Linux (glibc and musl, x86_64 and aarch64), Windows x86_64, macOS source-build only
- **Process model:** long-lived stream with ack callbacks on a background thread

For the non-blocking pattern, see [SKILL.md#step-4-build-the-producer](../SKILL.md#step-4-build-the-producer). Java methods: `ingestRecordOffset(Object)` queues and returns; `flush()` at the boundary; `close()` (try-with-resources) at shutdown. Java has an ack callback: `AckCallback` with `onAck(long offset)` and `onError(long offset, String msg)`.

## Installation

Add to `pom.xml`, and set `zerobus.version` to the latest release on [Maven Central](https://central.sonatype.com/artifact/com.databricks/zerobus-ingest-sdk). Look it up with `curl -s https://repo1.maven.org/maven2/com/databricks/zerobus-ingest-sdk/maven-metadata.xml | grep -o '<release>[^<]*'`. The sample below needs 1.6.0 or later.

```xml
<properties>
    <zerobus.version>LATEST_RELEASE</zerobus.version>  <!-- replace with the latest release from Maven Central -->
</properties>

<dependency>
    <groupId>com.databricks</groupId>
    <artifactId>zerobus-ingest-sdk</artifactId>
    <version>${zerobus.version}</version>
</dependency>
```

## JSON Ingestion

```java
import com.databricks.zerobus.AckCallback;
import com.databricks.zerobus.ZerobusJsonStream;
import com.databricks.zerobus.ZerobusSdk;

public class Producer {
    public static void main(String[] args) throws Exception {
        AckCallback progress = new AckCallback() {
            @Override public void onAck(long offsetId) {  // runs on an SDK thread; keep it fast
                System.out.println("durable through offset " + offsetId);
            }
            @Override public void onError(long offsetId, String errorMessage) {
                System.err.println("error at offset " + offsetId + ": " + errorMessage);
            }
        };
        try (ZerobusSdk sdk = new ZerobusSdk(
                 System.getenv("ZEROBUS_SERVER_ENDPOINT"), System.getenv("DATABRICKS_WORKSPACE_URL"));
             ZerobusJsonStream stream = sdk.streamBuilder()
                 .table(System.getenv("ZEROBUS_TABLE_NAME"))
                 .oauth(System.getenv("DATABRICKS_CLIENT_ID"), System.getenv("DATABRICKS_CLIENT_SECRET"))
                 .ackCallback(progress)
                 .json()
                 .build()
                 .join()) {
            for (int i = 0; i < 100; i++) {
                String record = String.format(
                    "{\"device_name\": \"sensor-%d\", \"temp\": %d}", i % 10, 20 + (i % 15));
                stream.ingestRecordOffset(record);  // queues, returns
            }
            stream.flush();  // durability boundary; close() runs at the end of the try block
        }
    }
}
```

**Verify:** The program compiles and runs. **Expected:** records land in the target table.

## Protobuf

For type safety, pass `.compiledProto(MyEvent.getDescriptor().toProto())` to the builder after `.oauth()`. See [protobuf-schema.md](protobuf-schema.md) to generate the `.proto` and compile it. Read the [Java SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md) for the complete Protobuf pattern.

## Arrow Flight

For vectorized columnar data (`ZerobusArrowStream`), add the opt-in dependencies `org.apache.arrow:arrow-vector` and `org.apache.arrow:arrow-memory-netty` (17.0.0 in the README), and on JDK 9+ pass both JVM flags:

```bash
java --add-opens=java.base/java.nio=ALL-UNNAMED \
     --add-opens=java.base/java.nio=org.apache.arrow.memory.core \
     -cp <classpath> <MainClass>
```

Arrow streams don't support ack callbacks. See [arrow-flight.md](arrow-flight.md) for the full pattern.

For the full API, ack callback usage, and more examples, read the [Java SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md).

## Sources

- [Java SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md)
- [Java SDK examples](https://github.com/databricks/zerobus-sdk/tree/main/java/examples)
