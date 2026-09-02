# `setup-local` examples

Use the selected profile and run both commands from the confirmed project directory.

## Cluster

If the cluster is unknown, list candidates and ask the user to choose:

```bash
databricks clusters list --profile <PROFILE> --output json |
  jq '.[] | {cluster_id, cluster_name, state, spark_version}'
```

Then preview and, after approval, apply with the selected ID:

```bash
databricks environments setup-local --profile <PROFILE> --cluster-id <CLUSTER_ID> --dry-run --output json
databricks environments setup-local --profile <PROFILE> --cluster-id <CLUSTER_ID> --output json
```

## Serverless

```bash
databricks environments setup-local --profile <PROFILE> --serverless-version 5 --dry-run --output json
databricks environments setup-local --profile <PROFILE> --serverless-version 5 --output json
```

Run the second command only after showing the preview and obtaining approval.
On success in a bundle, update existing job `environment_version` values to `"5"`, then validate the selected bundle target with the same profile.

## Job task

When the user knows the job but not its task key, inspect the job and present the keys:

```bash
databricks jobs get 123 --profile <PROFILE> --output json |
  jq -r '.settings.tasks[].task_key'
```

After the user selects `my_task`, preview, show the plan, and obtain approval before applying:

```bash
databricks environments setup-local --profile <PROFILE> --job-task 123.my_task --dry-run --output json
databricks environments setup-local --profile <PROFILE> --job-task 123.my_task --output json
```

## Bundle target

From the confirmed bundle root, omit the compute flag. Select a named bundle target with the global `--target` flag when needed:

```bash
databricks environments setup-local --profile <PROFILE> --dry-run --output json
databricks environments setup-local --profile <PROFILE> --target dev --dry-run --output json
```

After approval, repeat the chosen command without `--dry-run`.

## Representative JSON excerpts

These excerpts omit fields that do not affect the branch. A dry-run success includes the resolved target and proposed changes:

```json
{
  "schemaVersion": 1,
  "ok": true,
  "dryRun": true,
  "compute": {
    "source": "serverless",
    "serverlessVersion": "v4",
    "envKey": "serverless/serverless-v4"
  },
  "resolved": {
    "pythonVersion": "3.12",
    "dbconnectVersion": "17.2.0",
    "artifactSource": "network"
  },
  "plan": {
    "wouldWrite": "<PROJECT_DIR>/pyproject.toml",
    "wouldInstallPython": "3.12",
    "diff": "<UNIFIED_DIFF>"
  },
  "warnings": [],
  "error": null
}
```

A structured failure is still actionable and reports whether disk changed:

```json
{
  "schemaVersion": 1,
  "ok": false,
  "dryRun": false,
  "warnings": [],
  "error": {
    "code": "E_NO_TARGET",
    "failurePhase": "resolve",
    "message": "No compute target is selected...",
    "diskMutated": false
  }
}
```

Branch on `ok`, surface all warnings, and use [troubleshooting](troubleshooting.md) for failures.
