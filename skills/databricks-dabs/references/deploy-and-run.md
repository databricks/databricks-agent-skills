# Deploy and Run Declarative Automation Bundles

## Initialization

Start a new bundle interactively:

```bash
databricks bundle init
```

Built-in templates:

| Template             | Use for                                            |
| -------------------- | -------------------------------------------------- |
| `default-python`     | Python project with jobs and a pipeline            |
| `default-sql`        | SQL project with jobs                              |
| `default-scala`      | Scala/Java project                                 |
| `lakeflow-pipelines` | Lakeflow Declarative Pipelines (Python or SQL)     |
| `dbt-sql`            | dbt integration                                    |
| `default-minimal`    | Minimal bundle skeleton                            |

Pass a template name or a Git URL pointing at a template directory to skip the interactive picker.

## Generate from Existing Resources

If a workspace already has the resource, generate its bundle YAML instead of writing it by hand:

```bash
databricks bundle generate job <job-id>
databricks bundle generate pipeline <pipeline-id>
databricks bundle generate dashboard <dashboard-id>
databricks bundle generate app <app-name>
```

This writes a resource file under `resources/` plus any referenced source assets.

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

## Destroy

`bundle destroy` removes everything the bundle previously deployed to the target workspace. It is destructive; confirm the target before running it.

- `bundle destroy -t dev`
- `bundle destroy -t prod`

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
| **App not starting after deploy**  | Use `databricks apps deploy` (deploys *and* starts the app); a bare `bundle deploy` leaves it stopped. Or run `databricks bundle run <resource_key>` after deploy. |
| **App env vars not working**       | Environment variables go in `app.yaml` (source dir), not databricks.yml |
| **Debugging any app issue**        | First step: `databricks apps logs <app-name>`                           |
| **Variable shows as `${var.name}` literal** | Variable not declared in `databricks.yml` `variables:`, missing from the active target, or wrong syntax (use `${var.<name>}`) |
| **Validation errors unclear**      | Re-run with `databricks bundle validate --strict --debug`                |
