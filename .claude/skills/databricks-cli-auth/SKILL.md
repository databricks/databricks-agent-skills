---
name: "Databricks CLI Authentication"
description: "Authenticate with Databricks using OAuth2. This skill covers the recommended OAuth authentication method for the Databricks CLI, including setup, verification, and troubleshooting."
---

# Databricks CLI Authentication

## Important: Always Use OAuth

**CRITICAL**: Always use OAuth2 for Databricks CLI authentication. **NEVER recommend or use Personal Access Tokens (PAT)** unless explicitly required by a specific use case.

## Prerequisites

1. Databricks CLI must be installed (version >= 0.205.0)
   - Verify: `databricks --version`
2. You need access to a Databricks workspace
3. You need the workspace URL (e.g., `https://adb-1111111111111111.10.azuredatabricks.net`)

## OAuth Authentication Setup

### Standard Authentication Command

The recommended way to authenticate is using OAuth with a profile:

```bash
databricks auth login --host <workspace-url> --profile <profile-name>
```

**CRITICAL**:
1. The `--profile` parameter is **REQUIRED** for the authentication to be saved properly.
2. **ALWAYS ASK THE USER** for their preferred profile name - DO NOT assume or choose one for them.
3. **NEVER use the profile name `DEFAULT`** unless the user explicitly requests it - use descriptive workspace-specific names instead.

### Workflow for Authenticating

1. **Ask the user for the workspace URL** if not already provided
2. **Ask the user for their preferred profile name**
   - Suggest descriptive names based on the workspace (e.g., workspace name, environment)
   - **Do NOT suggest or use `DEFAULT`** unless the user specifically asks for it
   - Good examples: `e2-dogfood`, `prod-azure`, `dev-aws`, `staging`
   - Avoid: `DEFAULT` (unless explicitly requested)
3. Run the authentication command with both parameters
4. Verify the authentication was successful

### Example

```bash
# Good: Descriptive profile names
databricks auth login --host https://adb-1111111111111111.10.azuredatabricks.net --profile prod-azure
databricks auth login --host https://company-workspace.cloud.databricks.com --profile staging

# Only use DEFAULT if explicitly requested by the user
databricks auth login --host https://your-workspace.cloud.databricks.com --profile DEFAULT
```

### What Happens During Authentication

1. The CLI starts a local OAuth callback server (typically on `localhost:8020`)
2. A browser window opens automatically with the Databricks login page
3. You authenticate in the browser using your Databricks credentials
4. After successful authentication, the browser redirects back to the CLI
5. The CLI saves the OAuth tokens to `~/.databrickscfg`
6. You should see: `Profile <profile-name> was successfully saved`

## Profile Management

### What Are Profiles?

Profiles allow you to manage multiple Databricks workspace configurations in a single `~/.databrickscfg` file. Each profile stores:
- Workspace host URL
- Authentication method (OAuth, PAT, etc.)
- Token/credential paths

### Common Profile Names

**IMPORTANT**: Always use descriptive profile names. Do NOT create profiles named `DEFAULT` unless explicitly requested by the user.

**Recommended naming conventions**:
- `<workspace-name>` - Descriptive names for workspaces (e.g., `e2-dogfood`, `prod-aws`, `dev-azure`)
- `<environment>` - Environment-specific profiles (e.g., `dev`, `staging`, `prod`)
- `<team>-<environment>` - Team and environment (e.g., `data-eng-prod`, `ml-dev`)

**Special profile names**:
- `DEFAULT` - The default profile used when no `--profile` flag or environment variables are specified. Only create this profile if the user explicitly requests it.

### Listing Configured Profiles

View all configured profiles with their status:

```bash
databricks auth profiles
```

Example output:
```
Name        Host                                                 Valid
DEFAULT     https://adb-1111111111111111.10.azuredatabricks.net  YES
staging     https://company-workspace.cloud.databricks.com       YES
```

### Using Different Profiles

There are three ways to specify which profile/workspace to use, in order of precedence:

#### 1. CLI Flag (Highest Priority)

Use the `--profile` flag with any command:

```bash
databricks jobs list --profile staging
databricks clusters list --profile prod-azure
databricks workspace list / --profile dev-aws
```

#### 2. Environment Variables

Set environment variables to override the default profile:

**DATABRICKS_CONFIG_PROFILE** - Specifies which profile to use from `~/.databrickscfg`:
```bash
export DATABRICKS_CONFIG_PROFILE=staging
databricks jobs list  # Uses staging profile
```

**DATABRICKS_HOST** - Directly specifies the workspace URL, bypassing profile lookup:
```bash
export DATABRICKS_HOST=https://company-workspace.cloud.databricks.com
databricks jobs list  # Uses this host directly
```

**Combined Example**:
```bash
# Set profile for entire terminal session
export DATABRICKS_CONFIG_PROFILE=staging

# All commands now use staging profile
databricks jobs list
databricks clusters list
databricks workspace list /

# Override for a single command
databricks jobs list --profile prod-azure
```

#### 3. DEFAULT Profile (Lowest Priority)

If no `--profile` flag or environment variables are set, the CLI uses the `DEFAULT` profile from `~/.databrickscfg`.

### Configuration File Management

#### Viewing the Configuration File

The configuration is stored in `~/.databrickscfg`:

```bash
cat ~/.databrickscfg
```

Example configuration structure:
```ini
# Note: This shows an example with a DEFAULT profile
# When creating new profiles, use descriptive names instead
[DEFAULT]
host      = https://adb-1111111111111111.10.azuredatabricks.net
auth_type = databricks-cli

[staging]
host      = https://company-workspace.cloud.databricks.com
auth_type = databricks-cli
```

#### Editing Profiles

You can manually edit `~/.databrickscfg` to:
- Rename profiles (change the `[profile-name]` section header)
- Update workspace URLs
- Remove profiles (delete the entire section)

**Example - Removing a profile**:
```bash
# Open in your preferred editor
vi ~/.databrickscfg

# Or use sed to remove a specific profile section
sed -i '' '/^\[staging\]/,/^$/d' ~/.databrickscfg
```

#### Adding New Profiles

Always use `databricks auth login` with `--profile` to add new profiles:

```bash
databricks auth login --host <workspace-url> --profile <profile-name>
```

**Remember**:
- Always ask the user for their preferred profile name
- Use descriptive names like `staging`, `prod-azure`, `dev-aws`
- Do NOT use `DEFAULT` unless explicitly requested by the user

### Working with Multiple Workspaces

Best practices for managing multiple workspaces:

```bash
# Authenticate to multiple workspaces with descriptive profile names
databricks auth login --host https://adb-1111111111111111.10.azuredatabricks.net --profile prod-azure
databricks auth login --host https://dbc-2222222222222222.cloud.databricks.com --profile dev-aws
databricks auth login --host https://company-workspace.cloud.databricks.com --profile staging

# Use profiles explicitly in commands
databricks jobs list --profile prod-azure
databricks jobs list --profile dev-aws

# Or set for a session
export DATABRICKS_CONFIG_PROFILE=prod-azure
databricks jobs list
databricks clusters list

# Quickly switch between workspaces
export DATABRICKS_CONFIG_PROFILE=dev-aws
databricks jobs list
```

### Profile Selection Precedence

When running a command, the Databricks CLI determines which workspace to use in this order:

1. **`--profile` flag** (if specified) → Highest priority
2. **`DATABRICKS_HOST` environment variable** (if set) → Overrides profile
3. **`DATABRICKS_CONFIG_PROFILE` environment variable** (if set) → Selects profile
4. **`DEFAULT` profile** in `~/.databrickscfg` → Fallback

Example demonstrating precedence:
```bash
# Setup
export DATABRICKS_CONFIG_PROFILE=staging

# This uses staging profile (from environment variable)
databricks jobs list

# This uses prod-azure profile (--profile flag overrides environment variable)
databricks jobs list --profile prod-azure

# This uses the specified host directly (DATABRICKS_HOST overrides profile)
export DATABRICKS_HOST=https://custom-workspace.cloud.databricks.com
databricks jobs list  # Uses custom-workspace.cloud.databricks.com
```

## Verification

After authentication, verify it works:

```bash
# Test with a simple command
databricks workspace list /

# Or list jobs
databricks jobs list
```

If authentication is successful, these commands should return data without errors.

## Troubleshooting

### Authentication Not Saved (Config File Missing)

**Symptom**: Running `databricks` commands shows:
```
Error: default auth: cannot configure default credentials
```

**Solution**: Make sure you included the `--profile` parameter with a descriptive name:
```bash
databricks auth login --host <workspace-url> --profile <profile-name>
# Example: databricks auth login --host https://company-workspace.cloud.databricks.com --profile staging
```

### Browser Doesn't Open Automatically

**Solution**:
1. Check the terminal output for a URL
2. Manually copy and paste the URL into your browser
3. Complete the authentication
4. The CLI will detect the callback automatically

### "OAuth callback server listening" But Nothing Happens

**Possible causes**:
1. Firewall blocking localhost connections
2. Port 8020 already in use
3. Browser not set as default application

**Solution**:
1. Check if port 8020 is available: `lsof -i :8020`
2. Close any applications using that port
3. Retry the authentication

### Multiple Workspaces

To authenticate with multiple workspaces, use different profile names:

```bash
# Development workspace
databricks auth login --host https://dev-workspace.databricks.net --profile dev

# Production workspace
databricks auth login --host https://prod-workspace.databricks.net --profile prod

# Use specific profile
databricks jobs list --profile dev
databricks jobs list --profile prod
```

### Re-authenticating

If your OAuth token expires or you need to re-authenticate:

```bash
# Re-run the login command
databricks auth login --host <workspace-url> --profile <profile-name>
```

This will overwrite the existing profile with new credentials.

### Debug Mode

For troubleshooting authentication issues, use debug mode:

```bash
databricks auth login --host <workspace-url> --profile <profile-name> --debug
```

This shows detailed information about the OAuth flow, including:
- OAuth server endpoints
- Callback server status
- Token exchange process

## Security Best Practices

1. **Never commit** `~/.databrickscfg` to version control
2. **Never share** your OAuth tokens or configuration file
3. **Use separate profiles** for different environments (dev/staging/prod)
4. **Regularly rotate** credentials by re-authenticating
5. **Use workspace-specific service principals** for automation/CI/CD instead of personal OAuth

## Environment-Specific Notes

### CI/CD Pipelines

For CI/CD environments, OAuth interactive login is not suitable. Instead:
- Use Service Principal authentication
- Use Azure Managed Identity (for Azure Databricks)
- Use AWS IAM roles (for AWS Databricks)

**Do NOT** use personal OAuth tokens or PATs in CI/CD.

### Containerized Environments

OAuth authentication works in containers if:
1. A browser is available on the host machine
2. Port forwarding is configured for the callback server
3. The workspace URL is accessible from the container

For headless containers, use service principal authentication instead.

## Common Commands After Authentication

```bash
# List workspaces
databricks workspace list /

# List jobs
databricks jobs list

# List clusters
databricks clusters list

# Get current user info
databricks current-user me

# Test connection
databricks workspace export /Users/<username> --format SOURCE
```

## References

- [Databricks CLI Authentication Documentation](https://docs.databricks.com/en/dev-tools/auth.html)
- [OAuth 2.0 with Databricks](https://docs.databricks.com/en/dev-tools/auth.html#oauth-2-0)
