# Foundation Model API endpoints

Pay-per-token, pre-provisioned in every workspace. New models land regularly and a static skill list goes stale fast — **always list at runtime instead of hard-coding names**. Filter by the `databricks-` name prefix AND by the served entity being in `system.ai.*` (other endpoints like `databricks-app-template-serving` share the prefix but aren't FM API endpoints).

```bash
# Foundation Model API endpoints in this workspace, grouped by task (chat / embeddings / etc.)
databricks serving-endpoints list \
  | jq -r '.[]
      | select(.name | startswith("databricks-"))
      | select((.config.served_entities[0].entity_name // "") | startswith("system.ai."))
      | "\(.task)\t\(.name)"' \
  | sort
```

**Defaults when the user doesn't specify**: pick the highest-numbered Claude Sonnet for agents, the highest-numbered `-codex-max` for code, `databricks-gte-large-en` for embeddings — resolve actual names from the live list above.
