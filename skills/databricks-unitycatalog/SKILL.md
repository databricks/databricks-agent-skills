---
name: databricks-unitycatalog
description: "Unity Catalog governance operations: discovery, grants, volumes, external locations, and UC object workflows."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Unity Catalog

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Use this skill for Unity Catalog governance and day-2 operations: namespaces and objects, discovery, grants/privileges, volumes, external locations, storage credentials, lineage/observability, and UC-managed AI/ML objects.

## Required Reading by Task

| Task | READ BEFORE proceeding |
|------|------------------------|
| Discover catalogs/schemas/tables; search metadata | [Namespace & discovery](references/namespace-and-objects.md) |
| Grants, privileges, ownership/MANAGE, RLS/CLS | [Access control](references/access-control.md) |
| Read/write files via Volumes | [Volumes](references/volumes.md) |
| External locations, storage credentials, federation, sharing | [Storage & connections](references/storage-and-connections.md) |
| Lineage, tags, audit logs, cost attribution | [Lineage & observability](references/lineage-and-observability.md) |
| Maintenance, time travel, migration, constraints, clone | [Operations & migration](references/operations-and-migration.md) |
| Models, functions, vector search, feature tables | [AI & ML objects](references/ai-ml-objects.md) |

## Priorities (P1 → P3)

- **P1**: Access control (grants/privileges), volumes + external locations, and metadata discovery (`information_schema`)
- **P2**: Lineage/observability (tags, audit logs), federation/sharing patterns, and operational best practices
- **P3**: Billing and cost attribution patterns (system tables)

## Key gotchas (do not skip)

- **CLI args**: many UC list/get commands use **positional** arguments (see parent `databricks-core` quick reference).
- **File privileges**: **`WRITE FILES` requires `READ FILES`** (common cause of confusing permission errors).
- **Discovery without data**: `BROWSE` enables seeing objects without reading table data.
- **Ownership vs MANAGE**: these are not interchangeable; confirm which is required for the operation.

## Reference Guides

- [Namespace & discovery](references/namespace-and-objects.md)
- [Access control](references/access-control.md)
- [Volumes](references/volumes.md)
- [Storage & connections](references/storage-and-connections.md)
- [Lineage & observability](references/lineage-and-observability.md)
- [Operations & migration](references/operations-and-migration.md)
- [AI & ML objects](references/ai-ml-objects.md)
