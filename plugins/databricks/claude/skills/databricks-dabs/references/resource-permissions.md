# DABs Resource Permissions

## Permission Levels by Resource Type

| Resource       | Levels                                          | Field         |
| -------------- | ----------------------------------------------- | ------------- |
| **Dashboards** | `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` | `permissions` |
| **Jobs**       | `CAN_VIEW`, `CAN_MANAGE_RUN`, `CAN_MANAGE`      | `permissions` |
| **Pipelines**  | `CAN_VIEW`, `CAN_RUN`, `CAN_MANAGE`             | `permissions` |
| **Alerts**     | `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` | `permissions` |
| **Volumes**    | N/A — use `grants`                              | `grants`      |

## Standard Permission Block

```yaml
permissions:
  - level: CAN_VIEW
    group_name: 'users'
```

Use `"users"` for all workspace users.

## Volume Grants (Different Format)

Volumes use `grants` not `permissions`:

```yaml
resources:
  volumes:
    my_volume:
      catalog_name: ${var.catalog}
      schema_name: ${var.schema}
      name: 'volume_name'
      volume_type: 'MANAGED'
      # grants:
      #   - principal: "group_name"
      #     privileges:
      #       - "READ_VOLUME"
```

## Common Mistakes

| Issue                              | Solution                                                |
| ---------------------------------- | ------------------------------------------------------- |
| **Wrong permission level**         | Check the table above — levels differ per resource type |
| **"admins" group error on jobs**   | Cannot modify "admins" group permissions on jobs        |
| **Using `permissions` on volumes** | Use `grants` instead                                    |
| **Custom group doesn't exist**     | Verify custom groups exist in workspace before use      |
