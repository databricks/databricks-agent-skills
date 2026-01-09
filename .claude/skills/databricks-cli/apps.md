# Databricks Apps Development

## Validation

⚠️ **Always validate before deploying:**

```bash
databricks experimental aitools tools validate ./ --profile my-workspace
```

This is battle-tested to catch common issues before deployment. Prefer using this over manual checks (e.g. `npm run lint`), as it covers more ground specific to Databricks Apps.

## Deployment

⚠️ **USER CONSENT REQUIRED: Only deploy with explicit user permission.**

```bash
databricks experimental aitools tools deploy --profile my-workspace
```

## View and Manage

```bash
databricks bundle summary --profile my-workspace
```

## View App Logs

To troubleshoot deployed apps, view their logs:

```bash
databricks apps logs <app-name> --tail-lines 100 --profile my-workspace
```

## Local Development vs Deployed Apps

### During Development

- Start template-specific dev server (see project's CLAUDE.md for command and port)
- Use localhost URL shown when dev server starts

### After Deployment

- Get URL from: `databricks bundle summary --profile my-workspace`

### Decision Tree

- **"open the app"** + not deployed → localhost
- **"open the app"** + deployed → ask which environment
- **"localhost"/"local"** → always localhost

## Common Workflows

### Creating a New App

See [Project Scaffolding](projects.md) for creating new apps using templates.

### Updating an Existing App

1. Make changes to your code
2. Validate: `databricks experimental aitools tools validate ./ --profile my-workspace`
3. Get user consent to deploy
4. Deploy: `databricks experimental aitools tools deploy --profile my-workspace`
5. Check logs if issues occur: `databricks apps logs <app-name> --tail-lines 100 --profile my-workspace`

### Troubleshooting

1. Check validation output first
2. View app logs: `databricks apps logs <app-name> --tail-lines 100 --profile my-workspace`
3. Check bundle summary: `databricks bundle summary --profile my-workspace`
4. Verify app status: `databricks apps get <app-name> --profile my-workspace`

## Related Topics

- [Project Scaffolding](projects.md) - Create new apps with templates
- [Asset Bundles](asset-bundles.md) - Manage apps with Infrastructure-as-Code
- [Secrets](secrets.md) - Store credentials securely
