# Deploy and Run Declarative Automation Bundles

## Validation

Validate bundle configuration:

- `bundle validate --strict`
- `bundle validate --strict -t prod`

**Always validate with the `--strict` flag after any configuration change.** The `--strict` flag ensures that warnings are treated as errors, catching issues that would otherwise be missed.

## Deployment

Deploy:

- `bundle deploy`
- `bundle deploy -t prod`
- `bundle deploy --auto-approve`
- `bundle deploy --force`

For dev targets you can deploy without user consent. This allows you to run resources on the workspace too!

**Skip validation before deployment for dev targets.** Deployment itself will surface any issues, so a separate validation step is unnecessary.

## Running Resources

Run resources:

- `bundle run resource_name`
- `bundle run pipeline_name -t prod`
- `bundle run app_resource_key -t dev`

View status: `bundle summary`

## Monitoring and Logs

```bash
databricks apps logs <app-name> --profile <profile-name>
```

## Diagnosing Errors

- Read the error message from the CLI output to understand the issue, then inspect the relevant bundle files to diagnose the root cause.
- After diagnosing, provide a clear explanation and suggest concrete fixes.
- After fixing an error, validate the fix with the appropriate command:
  - `bundle summary` if the error was in summary
  - `bundle deploy` if the error was during deployment
  - `bundle validate --strict` otherwise

## Common Issues

| Issue                              | Solution                                                                |
| ---------------------------------- | ----------------------------------------------------------------------- |
| **Path resolution fails**          | Use `../src/` in resources/\*.yml, `./src/` in databricks.yml           |
| **Hardcoded catalog in dashboard** | Use dataset_catalog parameter (CLI v0.281.0+)                           |
| **App not starting after deploy**  | Apps require `databricks bundle run <resource_key>` to start            |
| **App env vars not working**       | Environment variables go in `app.yaml` (source dir), not databricks.yml |
| **Debugging any app issue**        | First step: `databricks apps logs <app-name>`                           |
