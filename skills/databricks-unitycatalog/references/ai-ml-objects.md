# AI & ML objects in Unity Catalog (models, functions, vector, features)

## When to use this reference

Use this doc when working with UC-governed AI/ML primitives:

- registered models
- UC functions (including those used as governed “tools”)
- vector search indexes
- feature tables and online store publishing (if applicable)

## Registered models (governance mindset)

UC can govern registered models and their lifecycle (versions, aliases/stages depending on setup). Treat model governance similarly to table governance:

- who can read / write / deploy
- how changes are audited
- how environments (dev/stage/prod) are separated

## UC functions as governed tools

UC functions can be a controlled “tool surface” when used intentionally.

Checklist:

- Add a clear `COMMENT` describing safe usage and inputs/outputs.
- Ensure callers have `EXECUTE` privilege (and only what they need).
- Avoid designs that require embedding secrets in function bodies or configs.

## Python UDFs / UDTFs (validate constraints early)

Support, packaging, and runtime constraints vary by environment. Validate:

- runtime compatibility
- dependency strategy (what can/can’t be packaged)
- permissions (who can create/alter/execute)

## Vector Search indexes

Common patterns:

- direct index over data
- Delta Sync-managed refresh

Pick based on freshness requirements and operational overhead.

## Feature tables / online store publishing

Typical workflow:

- curate feature tables with stable keys and definitions
- publish/sync to an online store (if used)

Confirm which feature APIs your workspace supports and which principal will run publish/sync jobs (human vs service principal).

## External access from functions/UDFs

If functions/UDFs access external cloud services:

- keep credentials out of code (no embedded tokens/secrets)
- confirm egress/networking policies allow access
- enforce least privilege and auditability
