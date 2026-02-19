# Secrets

Databricks Secrets provide secure storage for credentials and sensitive information.

## Secret Scopes

Secret scopes are containers for secrets.

### List Scopes

```bash
# List all secret scopes
databricks secrets list-scopes --profile my-workspace
```

### Create Scope

```bash
# Create a secret scope
databricks secrets create-scope --scope <scope-name> --profile my-workspace

# Create with initial ACL (Databricks-managed)
databricks secrets create-scope \
  --scope <scope-name> \
  --initial-manage-principal users \
  --profile my-workspace
```

### Delete Scope

```bash
# Delete a secret scope (deletes all secrets in it)
databricks secrets delete-scope --scope <scope-name> --profile my-workspace
```

**Warning**: This permanently deletes all secrets in the scope.

## Managing Secrets

### List Secrets

```bash
# List secrets in a scope
databricks secrets list --scope <scope-name> --profile my-workspace
```

**Note**: Only lists secret names, not values.

### Put Secret

```bash
# Put secret from string value
databricks secrets put \
  --scope <scope-name> \
  --key <secret-key> \
  --string-value <secret-value> \
  --profile my-workspace

# Put secret from file
databricks secrets put-secret \
  --scope <scope-name> \
  --key <secret-key> \
  --binary-file /path/to/file \
  --profile my-workspace
```

### Delete Secret

```bash
# Delete a secret
databricks secrets delete \
  --scope <scope-name> \
  --key <secret-key> \
  --profile my-workspace
```

## Secret ACLs (Access Control Lists)

Control who can access secrets in a scope.

### List ACLs

```bash
# List ACLs for a scope
databricks secrets list-acls --scope <scope-name> --profile my-workspace

# Get ACL for specific principal
databricks secrets get-acl \
  --scope <scope-name> \
  --principal <user-or-group> \
  --profile my-workspace
```

### Put ACL

```bash
# Grant READ permission
databricks secrets put-acl \
  --scope <scope-name> \
  --principal <user-or-group> \
  --permission READ \
  --profile my-workspace

# Grant WRITE permission
databricks secrets put-acl \
  --scope <scope-name> \
  --principal <user-or-group> \
  --permission WRITE \
  --profile my-workspace

# Grant MANAGE permission
databricks secrets put-acl \
  --scope <scope-name> \
  --principal <user-or-group> \
  --permission MANAGE \
  --profile my-workspace
```

### Delete ACL

```bash
# Remove ACL for a principal
databricks secrets delete-acl \
  --scope <scope-name> \
  --principal <user-or-group> \
  --profile my-workspace
```

## Permissions

- **READ**: Can read secret values
- **WRITE**: Can create/update secrets
- **MANAGE**: Can create/update secrets and manage ACLs

## Using Secrets

### In Notebooks

```python
# Get secret value
db_password = dbutils.secrets.get(scope="my-secrets", key="db-password")

# Use in connection
jdbc_url = "jdbc:postgresql://host/db"
df = spark.read \
  .format("jdbc") \
  .option("url", jdbc_url) \
  .option("user", dbutils.secrets.get("my-secrets", "db-user")) \
  .option("password", dbutils.secrets.get("my-secrets", "db-password")) \
  .load()
```

### In Spark Configuration

```python
# Configure AWS access
spark.conf.set(
  "fs.s3a.access.key",
  dbutils.secrets.get("aws-secrets", "access-key")
)
spark.conf.set(
  "fs.s3a.secret.key",
  dbutils.secrets.get("aws-secrets", "secret-key")
)
```

### In Jobs

```json
{
  "spark_conf": {
    "fs.s3a.access.key": "{{secrets/aws-secrets/access-key}}",
    "fs.s3a.secret.key": "{{secrets/aws-secrets/secret-key}}"
  }
}
```

### In Model Serving

```json
{
  "external_model": {
    "openai_config": {
      "openai_api_key": "{{secrets/my-scope/openai-key}}"
    }
  }
}
```

## Common Use Cases

### Database Credentials

```bash
# Create scope for database credentials
databricks secrets create-scope --scope database-creds --profile my-workspace

# Store credentials
databricks secrets put \
  --scope database-creds \
  --key postgres-user \
  --string-value "db_user" \
  --profile my-workspace

databricks secrets put \
  --scope database-creds \
  --key postgres-password \
  --string-value "secure_password" \
  --profile my-workspace
```

### API Keys

```bash
# Create scope for API keys
databricks secrets create-scope --scope api-keys --profile my-workspace

# Store API keys
databricks secrets put \
  --scope api-keys \
  --key openai-key \
  --string-value "sk-..." \
  --profile my-workspace

databricks secrets put \
  --scope api-keys \
  --key stripe-key \
  --string-value "sk_live_..." \
  --profile my-workspace
```

### Cloud Storage Credentials

```bash
# Create scope for cloud credentials
databricks secrets create-scope --scope cloud-storage --profile my-workspace

# Store AWS credentials
databricks secrets put \
  --scope cloud-storage \
  --key aws-access-key \
  --string-value "AKIA..." \
  --profile my-workspace

databricks secrets put \
  --scope cloud-storage \
  --key aws-secret-key \
  --string-value "..." \
  --profile my-workspace
```

### SSH Keys

```bash
# Store SSH private key from file
databricks secrets put-secret \
  --scope ssh-keys \
  --key github-deploy-key \
  --binary-file ~/.ssh/id_rsa \
  --profile my-workspace
```

## Best Practices

### 1. Use Descriptive Scope Names

```bash
# ✅ Good: Descriptive names
databricks secrets create-scope --scope prod-database-creds
databricks secrets create-scope --scope external-api-keys
databricks secrets create-scope --scope aws-production

# ❌ Avoid: Generic names
databricks secrets create-scope --scope secrets1
databricks secrets create-scope --scope test
```

### 2. Organize by Environment

```bash
# Separate scopes for environments
databricks secrets create-scope --scope dev-credentials
databricks secrets create-scope --scope staging-credentials
databricks secrets create-scope --scope prod-credentials
```

### 3. Use Least Privilege

Grant only necessary permissions:

```bash
# Data scientists: READ only
databricks secrets put-acl \
  --scope prod-credentials \
  --principal data-science-team \
  --permission READ

# Admins: MANAGE
databricks secrets put-acl \
  --scope prod-credentials \
  --principal admins \
  --permission MANAGE
```

### 4. Never Log Secrets

```python
# ❌ NEVER do this
password = dbutils.secrets.get("my-scope", "password")
print(f"Password is: {password}")  # DON'T LOG!

# ✅ Good: Use directly without logging
password = dbutils.secrets.get("my-scope", "password")
# Use password in connections/configurations
```

### 5. Rotate Secrets Regularly

```bash
# Update secret with new value
databricks secrets put \
  --scope prod-credentials \
  --key api-key \
  --string-value "new_key_value" \
  --profile my-workspace
```

### 6. Use Key Vault for Production

For production workloads, use cloud provider key vaults:

**Azure Key Vault**:
```bash
# Create Azure Key Vault-backed scope
databricks secrets create-scope \
  --scope my-keyvault-scope \
  --scope-backend-type AZURE_KEYVAULT \
  --resource-id /subscriptions/.../resourceGroups/.../providers/Microsoft.KeyVault/vaults/my-keyvault \
  --dns-name https://my-keyvault.vault.azure.net/ \
  --profile my-workspace
```

**AWS Secrets Manager**: Similar integration available.

### 7. Document Secret Keys

Keep documentation of what each secret contains:

```bash
# Create scope with clear purpose
databricks secrets create-scope --scope ml-model-api-keys --profile my-workspace

# Use descriptive key names
databricks secrets put --scope ml-model-api-keys --key openai-gpt4-production-key
databricks secrets put --scope ml-model-api-keys --key huggingface-inference-token
```

## Security Best Practices

### 1. Never Commit Secrets to Git

```bash
# .gitignore
*.env
.env.*
secrets.json
credentials.txt
```

### 2. Limit Secret Scope Access

```bash
# Only grant access to teams that need it
databricks secrets put-acl \
  --scope sensitive-data \
  --principal authorized-team \
  --permission READ
```

### 3. Audit Secret Access

Regularly review:
- Who has access to secrets
- When secrets were last accessed
- Which secrets exist

```bash
# Review scopes
databricks secrets list-scopes --profile my-workspace

# Review ACLs
databricks secrets list-acls --scope my-scope --profile my-workspace
```

### 4. Use Different Scopes for Different Purposes

```bash
# Separate by purpose and sensitivity
databricks secrets create-scope --scope production-db-credentials
databricks secrets create-scope --scope third-party-api-keys
databricks secrets create-scope --scope internal-service-tokens
```

## Troubleshooting

### Cannot Create Scope

**Symptom**: Scope creation fails

**Solution**:
1. Check if scope name already exists
2. Verify you have permissions to create scopes
3. Ensure scope name meets naming requirements
4. Contact workspace admin if needed

### Cannot Access Secret

**Symptom**: `Error: User does not have READ permission`

**Solution**:
1. Check ACLs: `databricks secrets list-acls --scope <scope>`
2. Verify you or your group has READ permission
3. Ask scope owner to grant access
4. Check you're using correct scope name

### Secret Not Found

**Symptom**: `Error: Secret does not exist`

**Solution**:
1. List secrets: `databricks secrets list --scope <scope>`
2. Verify scope name is correct
3. Check key name is correct (case-sensitive)
4. Ensure secret was created

### ACL Changes Not Taking Effect

**Symptom**: Permission changes don't work

**Solution**:
1. Wait a few moments for propagation
2. Restart notebook/cluster if using in notebook
3. Verify ACL was set correctly
4. Check for typos in principal names

## Scope Backends

### Databricks-Managed (Default)

Secrets stored and managed by Databricks.

```bash
databricks secrets create-scope --scope my-scope --profile my-workspace
```

### Azure Key Vault

Secrets stored in Azure Key Vault.

```bash
databricks secrets create-scope \
  --scope my-keyvault-scope \
  --scope-backend-type AZURE_KEYVAULT \
  --resource-id <keyvault-resource-id> \
  --dns-name <keyvault-dns-name> \
  --profile my-workspace
```

**Advantages**:
- Enterprise key management
- Additional security features
- Compliance requirements
- Centralized secrets across services

## Related Topics

- [Data Exploration](data-exploration.md) - Query data that relies on secret-backed access
- [DBSQL](dbsql.md) - Secure warehouse and query integrations
- [Asset Bundles](asset-bundles.md) - Define and deploy resources that depend on secrets
