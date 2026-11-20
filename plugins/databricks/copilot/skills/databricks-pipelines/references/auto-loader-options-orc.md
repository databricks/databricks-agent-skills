ORC-Specific Options

**Important:** Auto Loader does NOT support schema inference or evolution for ORC. You MUST provide an explicit schema (via `.schema(...)` in Python or `schema` argument in `read_files`). Schema hints (`cloudFiles.schemaHints`) and `cloudFiles.inferColumnTypes` have no effect for ORC.

| Option      | Type    | Notes                                                |
| ----------- | ------- | ---------------------------------------------------- |
| mergeSchema | Boolean | Merge schemas across ORC files (expensive when true) |
