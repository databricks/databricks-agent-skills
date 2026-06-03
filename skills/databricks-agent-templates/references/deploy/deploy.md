> **Related skills:** For general Databricks Asset Bundle (DAB) authoring and resource management, use `databricks-dabs`; for the Databricks Apps platform itself, use `databricks-apps`. This skill covers only deploying an agent template to Databricks Apps.

# Deploy to Databricks Apps

## Profile Configuration

**IMPORTANT:** Before running any `databricks` CLI command, read the `.env` file to get the `DATABRICKS_CONFIG_PROFILE` value. All commands must include the profile:

```bash
databricks <command> --profile <profile>
```

For example, if `.env` has `DATABRICKS_CONFIG_PROFILE=dev`, run `databricks bundle deploy --profile dev`. Without this, the CLI may target the wrong workspace.

## App Naming Convention

Unless the user specifies a different name, apps should use the prefix `agent-*`:
- `agent-data-analyst`
- `agent-customer-support`
- `agent-code-helper`

Update the app name in `databricks.yml`:
```yaml
resources:
  apps:
    my_agent:
      name: "agent-your-app-name"  # Use agent-* prefix
```

## Deploy Commands

**IMPORTANT:** Run the pre-flight check before deploying to catch errors early, then run commands to deploy and start your app:

```bash
# 1. Pre-flight check (starts server locally, sends test request, verifies response)
uv run preflight

# 2. Validate bundle configuration (catches config errors before deploy)
databricks bundle validate

# 3. Deploy the bundle (creates/updates resources, uploads files)
databricks bundle deploy

# 4. Run the app (starts/restarts with uploaded source code) - REQUIRED!
databricks bundle run my_agent
```

> **Note:** `bundle deploy` only uploads files and configures resources. `bundle run` is **required** to actually start/restart the app with the new code. If you only run `deploy`, the app will continue running old code!

The resource key `my_agent` matches the app name in `databricks.yml` under `resources.apps`.

## Handling "App Already Exists" Error

If `databricks bundle deploy` fails with:
```
Error: failed to create app
Failed to create app <app-name>. An app with the same name already exists.
```

**Ask the user:** "Would you like to bind the existing app to this bundle, or delete it and create a new one?"

### Option 1: Bind Existing App (Recommended)

**Step 1:** Get the existing app's full configuration:
```bash
# Get app config including budget_policy_id and other server-side settings
databricks apps get <existing-app-name> --output json | jq '{name, budget_policy_id, description}'
```

**Step 2:** Update `databricks.yml` to match the existing app's configuration exactly:
```yaml
resources:
  apps:
    my_agent:
      name: "existing-app-name"  # Must match exactly
      budget_policy_id: "xxx-xxx-xxx"  # Copy from step 1 if present
```

> **Why this matters:** Existing apps may have server-side configuration (like `budget_policy_id`) that isn't in your bundle. If these don't match, Terraform will fail with "Provider produced inconsistent result after apply". Always sync the app's current config to `databricks.yml` before binding.

**Step 3:** If deploying to a `mode: production` target, set `workspace.root_path`:
```yaml
targets:
  prod:
    mode: production
    workspace:
      root_path: /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}
```

> **Why this matters:** Production mode requires an explicit root path to ensure only one copy of the bundle is deployed. Without this, the deploy will fail with a recommendation to set `workspace.root_path`.

**Step 4:** Check if already bound, then bind if needed:
```bash
# Check if resource is already managed by this bundle
databricks bundle summary --output json | jq '.resources.apps'

# If the app appears in the summary, skip binding and go to Step 5
# If NOT in summary, bind the resource:
databricks bundle deployment bind my_agent <existing-app-name> --auto-approve
```

> **Note:** If bind fails with "Resource already managed by Terraform", the app is already bound to this bundle. Skip to Step 5 and deploy directly.

**Step 5:** Deploy:
```bash
databricks bundle deploy
databricks bundle run my_agent
```

### Option 2: Delete and Recreate

```bash
databricks apps delete <app-name>
databricks bundle deploy
```

**Warning:** This permanently deletes the app's URL, OAuth credentials, and service principal.

## Unbinding an App

To remove the link between bundle and deployed app:

```bash
databricks bundle deployment unbind my_agent
```

Use when:
- Switching to a different app
- Letting bundle create a new app
- Switching between deployed instances

Note: Unbinding doesn't delete the deployed app.

## Query Deployed App

> **IMPORTANT:** Databricks Apps are **only** queryable via OAuth token. You **cannot** use a Personal Access Token (PAT) to query your agent. Attempting to use a PAT will result in a 302 redirect error.

**Get OAuth token:**
```bash
databricks auth token | jq -r '.access_token'
```

**Send request:**
```bash
curl -X POST <app-url>/invocations \
  -H "Authorization: Bearer <oauth-token>" \
  -H "Content-Type: application/json" \
  -d '{ "input": [{ "role": "user", "content": "hi" }], "stream": true }'
```

**If using memory** - include `user_id` to scope memories per user:
```bash
curl -X POST <app-url>/invocations \
  -H "Authorization: Bearer <oauth-token>" \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "What do you remember about me?"}],
      "custom_inputs": {"user_id": "user@example.com"}
  }'
```

## On-Behalf-Of (OBO) User Authentication

To authenticate as the requesting user instead of the app service principal:

```python
from agent_server.utils import get_user_workspace_client

# In your agent code
user_client = get_user_workspace_client()
# Use user_client for operations that should run as the user
```

This is useful when you want the agent to access resources with the user's permissions rather than the app's service principal permissions.

See: [OBO authentication documentation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth#retrieve-user-authorization-credentials)

## Debug Deployed Apps

```bash
# View logs (follow mode)
databricks apps logs <app-name> --follow

# Check app status
databricks apps get <app-name> --output json | jq '{app_status, compute_status}'

# Get app URL
databricks apps get <app-name> --output json | jq -r '.url'
```

## Post-Deploy: Autoscaling Lakebase Resources

If the agent uses **autoscaling Lakebase** (user mentions "autoscaling", "project", or "branch" in the context of Lakebase), the postgres resource is declared natively in `databricks.yml` — `databricks bundle deploy` creates the app with it. You only need to grant table permissions to the app's service principal after deploy:

```bash
# Find the SP client ID
databricks apps get <name> --output json | jq -r '.service_principal_client_id'

# Grant table permissions (see scripts/grant_lakebase_permissions.py)
```

**See `.claude/skills/add-tools/examples/lakebase-autoscaling.yaml` for the full resource snippet.** Requires CLI v0.295.0+ for native `postgres` resource support.

## Important Notes

- **App naming convention**: App names must be prefixed with `agent-` (e.g., `agent-my-assistant`, `agent-data-analyst`)
- **Name is immutable**: Changing the `name` field in `databricks.yml` forces app replacement (destroy + create)
- **Remote Terraform state**: Databricks stores state remotely; same app detected across directories
- **Review the plan**: Look for `# forces replacement` in Terraform output before confirming

## FAQ

**Q: I see a 200 OK in the logs, but get an error in the actual stream. What's going on?**

This is expected behavior. The initial 200 OK confirms stream setup was successful. Errors that occur during streaming don't affect the initial HTTP status code. Check the stream content for the actual error message.

**Q: When querying my agent, I get a 302 redirect error. What's wrong?**

You're likely using a Personal Access Token (PAT). Databricks Apps only support OAuth tokens. Generate one with:
```bash
databricks auth token
```

**Q: How do I add dependencies to my agent?**

Use `uv add`:
```bash
uv add <package_name>
# Example: uv add "mlflow-skinny[databricks]"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Validation errors | Run `databricks bundle validate` to see detailed errors before deploying |
| Permission errors at runtime | Grant resources in `databricks.yml` (see **add-tools** skill) |
| Lakebase access errors | See [`lakebase-setup`](../lakebase-setup/lakebase-setup.md) reference for permissions (if using memory) |
| App not starting | Check `databricks apps logs <app-name>` |
| Auth token expired | Run `databricks auth token` again |
| 302 redirect error | Use OAuth token, not PAT |
| "Provider produced inconsistent result" | Sync app config to `databricks.yml` |
| "should set workspace.root_path" | Add `root_path` to production target |
| App running old code after deploy | Run `databricks bundle run my_agent` after deploy |
| Env var is None in deployed app | Check `value_from` in databricks.yml `config.env` matches resource `name` |
