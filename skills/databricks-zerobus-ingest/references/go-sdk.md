# Go SDK

Read this when the producer is written in **Go**. Pick the variant: **CGO** (`go/`, Go 1.21+) for prebuilt libraries, or **pure Go** (`purego/`, Go 1.25+) when precompiled binaries or cgo aren't allowed.

**Record formats:** JSON and Protobuf in both variants; Arrow Flight in cgo only ([SKILL.md](../SKILL.md#sdks-record-formats-and-working-examples), from the SDK README's Ingestion APIs table).

For the non-blocking pattern, see [SKILL.md#step-4-build-the-producer](../SKILL.md#step-4-build-the-producer). Go methods queue and return: **cgo** uses `IngestRecordOffset(payload)` with `[]byte` or `string` (select JSON with `options.RecordType = zerobus.RecordTypeJson`); **pure Go** uses `IngestJSONOffset([]byte)` for JSON and `IngestRecordOffset([]byte)` for Protobuf. Both: `Flush()` at the boundary, `Close()` at shutdown. Pure Go has ack callbacks with `WithAckCallback`; CGO documents no callback.

## Installation

```bash
go get github.com/databricks/zerobus-sdk/go@latest      # CGO variant
go get github.com/databricks/zerobus-sdk/purego/zerobus@latest  # Pure Go
```

## CGO JSON Example

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"

	zerobus "github.com/databricks/zerobus-sdk/go"
)

func main() {
	sdk, err := zerobus.NewZerobusSdk(os.Getenv("ZEROBUS_SERVER_ENDPOINT"), os.Getenv("DATABRICKS_WORKSPACE_URL"))
	if err != nil {
		log.Fatal(err)
	}
	defer sdk.Free()

	options := zerobus.DefaultStreamConfigurationOptions()
	options.RecordType = zerobus.RecordTypeJson // the default is Protobuf
	stream, err := sdk.CreateStream(
		zerobus.TableProperties{TableName: os.Getenv("ZEROBUS_TABLE_NAME")},
		os.Getenv("DATABRICKS_CLIENT_ID"),
		os.Getenv("DATABRICKS_CLIENT_SECRET"),
		options,
	)
	if err != nil {
		log.Fatal(err)
	}
	defer stream.Close()

	for i := 0; i < 100; i++ {
		payload, err := json.Marshal(map[string]interface{}{
			"device_name": fmt.Sprintf("sensor-%d", i%10),
			"temp":        20 + (i % 15),
		})
		if err != nil {
			log.Fatal(err)
		}
		if _, err := stream.IngestRecordOffset(payload); err != nil { // queues, returns; []byte or string only
			log.Fatal(err)
		}
	}
	if err := stream.Flush(); err != nil { // durability boundary
		log.Fatal(err)
	}
}
```

**Verify:** compiles with `go build` and runs. **Expected:** records land in the target table.

## Variant Comparison

| Aspect | CGO (`go/`) | Pure Go (`purego/`) |
|--------|-------------|-------------------|
| **Import path** | `github.com/databricks/zerobus-sdk/go` | `github.com/databricks/zerobus-sdk/purego/zerobus` |
| **Go version** | 1.21+ | 1.25+ |
| **Native binaries needed** | Yes (statically linked) | No |
| **Ack callbacks** | No | Yes: `WithAckCallback` |
| **Arrow Flight** | Supported | Not supported |

See the [CGO README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md) and [purego README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/purego/README.md) for details.

For the full API, examples, and advanced patterns, read the [CGO README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md) or [purego README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/purego/README.md).

## Sources

- [CGO SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md)
- [CGO SDK examples](https://github.com/databricks/zerobus-sdk/tree/main/go/examples)
- [purego SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/purego/README.md)
- [purego SDK examples](https://github.com/databricks/zerobus-sdk/tree/main/purego/examples)
