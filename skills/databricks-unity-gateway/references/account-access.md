# Account Access

Some Unity Gateway tasks are account-scoped and cannot be done with a workspace profile:

- Groups used as Unity Catalog grant principals must be account-level groups. A
  workspace-local group is not a valid UC principal, so grants to it fail.
- Account budgets and spend alerts ([Budgets](budgets.md)).

## Authenticate at the account level

An account profile is separate from a workspace profile:

```bash
databricks auth login \
  --host <account-console-host> \
  --account-id <ACCOUNT_ID> \
  --profile <ACCOUNT_PROFILE>
```

| Cloud | Account console host |
|---|---|
| AWS | `https://accounts.cloud.databricks.com` |
| Azure | `https://accounts.azuredatabricks.net` |
| GCP | `https://accounts.gcp.databricks.com` |

## Confirm the level and permissions first

Before making an account-scoped change, verify the profile:

```bash
# Host must be the account console and account_id must be set.
databricks auth describe --profile <ACCOUNT_PROFILE>

# PERMISSION_DENIED means the identity is not an account admin.
databricks account groups list --profile <ACCOUNT_PROFILE>
```

If no account profile is configured, or the identity is not an account admin, do not
attempt the change. Respond with the exact commands, the required role (account admin),
and the authentication steps above so the user or an account admin can run them.

## Restrict a group to one model service

1. Create or select an account-level group (`databricks account groups create` /
   `list`) and confirm it is assigned to the workspace.
2. Grant query access on the model service and its parents; see
   [Permissions](permissions.md). Granting on an existing service such as
   `system.ai.<model>` is enough; a new model service is not required.
3. Check the group's other access paths and flag or remove anything broader, such as
   inherited `EXECUTE` on the parent schema, legacy serving endpoint `CAN_QUERY`, model
   provider services, and connections.
