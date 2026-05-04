# Storage & connections (credentials, external locations, federation, sharing)

## When to use this reference

Use this doc when you’re working with governed access to storage and external systems:

- storage credentials (identity used to access cloud storage)
- external locations (governed mapping to cloud paths)
- federation / foreign catalogs via connections
- Delta Sharing as provider or recipient

## Storage credentials (what they are)

Storage credentials define **how Databricks authenticates to cloud storage** for governed access. Commonly backed by:

- managed identity
- service principal

Keep all examples obfuscated (no real workspace URLs, account names, or IDs).

## External locations (the key governance primitive)

External locations bind a cloud storage URL to a UC securable so permissions can be managed centrally.

### Operational guidelines

- Validate location access at creation time where possible.
- Use **read-only** locations for shared datasets.
- For write-enabled locations, explicitly grant file privileges.

### Gotcha: file privileges

**`WRITE FILES` requires `READ FILES`**. Always grant both when enabling writes.

## Federation / foreign catalogs (via connections)

Connections can expose external systems as foreign catalogs. Before building workflows:

- confirm supported operations (read-only vs read/write)
- confirm identity and credential scope used by the connection
- confirm performance expectations and pushdown behavior

## Iceberg REST catalog (optional integration)

Iceberg REST catalog support (especially writes) varies by workspace and connector maturity. Treat as an optional integration and verify current support before committing to it.

## Delta Sharing (provider/recipient mental model)

Objects and workflows include:

- providers
- shares
- recipients
- token rotation / credential hygiene

Troubleshooting checklist:

- Identify the role: **provider** vs **recipient**
- Identify which principal is used (human, service principal, workspace identity)
- Confirm that the recipient’s token/credentials are current and stored securely (no embedded secrets in code)
