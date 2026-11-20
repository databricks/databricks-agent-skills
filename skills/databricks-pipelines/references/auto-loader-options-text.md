TEXT-Specific Options

**Important:** TEXT has a fixed schema (single column named `value` of type `STRING`). Schema inference and `cloudFiles.inferColumnTypes` do not apply, but partition column inference still works. Set `cloudFiles.schemaLocation` to avoid re-inferring partitions on each start.

| Option    | Type    | Notes                                                               |
| --------- | ------- | ------------------------------------------------------------------- |
| encoding  | String  | Default `UTF-8`. Affects line-separator decoding only, not content. |
| lineSep   | String  | Default covers `\r`, `\r\n`, `\n`.                                  |
| wholeText | Boolean | If `true`, read each file as a single record (one row per file).    |
