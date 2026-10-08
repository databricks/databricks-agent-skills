# Budgets and Spend Alerts

Spend budgets on Unity Gateway usage are account budget configurations created through the
account Budgets API. This is an account-admin operation; read
[Account access](account-access.md) before creating one.

Do not use a serverless budget policy (`databricks account budget-policy`) for this. Budget
policies tag serverless usage for attribution; they do not alert on Unity Gateway spend.

## Shape

- `resource_type: BUDGET_RESOURCE_TYPE_UNITY_AI_GATEWAY` scopes the budget to Unity Gateway
  spend. `BUDGET_RESOURCE_TYPE_ALL_RESOURCES` tracks all spend.
- `filter` narrows usage. Scope a product with a `databricks-product` tag (for example
  `genie`) and a workspace with `workspace_id`. Tags are case-sensitive.
- `alert_configurations` defines when to notify. A budget alert notifies; it does not cap or
  block usage.

## Create a monthly email alert

```json
{
  "budget": {
    "display_name": "genie-monthly-100",
    "resource_type": "BUDGET_RESOURCE_TYPE_UNITY_AI_GATEWAY",
    "filter": {
      "workspace_id": {"operator": "IN", "values": [<WORKSPACE_ID>]},
      "tags": [
        {"key": "databricks-product", "value": {"operator": "IN", "values": ["genie"]}}
      ]
    },
    "alert_configurations": [
      {
        "time_period": "MONTH",
        "trigger_type": "CUMULATIVE_SPENDING_EXCEEDED",
        "quantity_type": "LIST_PRICE_DOLLARS_USD",
        "quantity_threshold": "100",
        "action_configurations": [
          {"action_type": "EMAIL_NOTIFICATION", "target": "<EMAIL>"}
        ]
      }
    ]
  }
}
```

```bash
databricks account budgets create --json @budget.json --profile <ACCOUNT_PROFILE>
```

The REST equivalent is `POST <account-console-host>/api/2.1/accounts/<ACCOUNT_ID>/budgets`
with the same body.
