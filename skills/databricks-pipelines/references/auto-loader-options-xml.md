XML-Specific Options

**Key gotchas / tricks:**

- `rowTag` is **REQUIRED**. Set it to the XML tag that delimits one logical record (e.g., `<book>` in a `<books><book>...</book></books>` document → `rowTag => 'book'`).
- XML schema inference / evolution is supported in DBR 14.3 LTS and above (older runtimes will fail).
- `attributePrefix` (default `_`): XML attributes are flattened into columns prefixed with this string. Set to `""` to drop the prefix (read-only).
- `valueTag` (default `_VALUE`): name of the synthetic column for character data inside elements that ALSO have attributes/children. Auto Loader auto-adds this during schema inference when needed.
- `singleVariantColumn`: like JSON, ingest each record as a single Variant column — robust to schema drift.
- `rowValidationXSDPath`: rows that fail XSD validation are treated as parse errors (go to `_corrupt_record` / rescued column).

| Option                    | Type    |
| ------------------------- | ------- |
| rowTag                    | String  |
| samplingRatio             | Double  |
| excludeAttribute          | Boolean |
| mode                      | String  |
| inferSchema               | Boolean |
| columnNameOfCorruptRecord | String  |
| attributePrefix           | String  |
| valueTag                  | String  |
| encoding                  | String  |
| ignoreSurroundingSpaces   | Boolean |
| rowValidationXSDPath      | String  |
| ignoreNamespace           | Boolean |
| timestampFormat           | String  |
| timestampNTZFormat        | String  |
| dateFormat                | String  |
| locale                    | String  |
| rootTag                   | String  |
| declaration               | String  |
| arrayElementName          | String  |
| nullValue                 | String  |
| compression               | String  |
| validateName              | Boolean |
| readerCaseSensitive       | Boolean |
| rescuedDataColumn         | String  |
| singleVariantColumn       | String  |
