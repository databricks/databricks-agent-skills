---
description: "Read-only Databricks health check: CLI, profiles, auth validity via one API call. Pass `full` to also check compute and recent job failures."
argument-hint: "[profile] [full]"
allowed-tools: Bash(databricks:*), Read
---

# Databricks Doctor

Run a **read-only** health check and report a short status table. Make no
changes; every step below only reads. If a subcommand or flag is unfamiliar,
check `databricks <group> --help` first rather than guessing.

Run these in order. Don't stop on the first failure; collect what you can and
report the rest as unknown.

1. **CLI**: `databricks --version`. Flag only if it's missing; don't gate on a
   specific version (the CLI surfaces its own update notice).
2. **Profiles**: `databricks auth profiles`. List configured profiles and
   validity. If `$1` is given, use that profile for the rest. Otherwise, if more
   than one profile exists, ask the user which to use (**never auto-select**).
3. **Auth method**: `databricks auth describe --profile <profile>` shows the
   effective host, user, and credential source (never pass `--sensitive`).
4. **Auth validity**: `databricks current-user me --profile <profile>`. This
   single API call proves the credentials work end to end (token valid,
   workspace reachable, expected identity); don't probe other APIs for it.
   For account-level profiles (an `accounts.*` host), `current-user me` does
   not exist; report what `auth describe` resolved instead.

Stop here by default. Run the extended checks below only when the user passed
`full` or asked about compute or jobs:

5. **Compute**: `databricks warehouses list` and `databricks clusters list` for
   the profile. Note what's running.
6. **Recent job failures**: list recent job runs (e.g.
   `databricks jobs list-runs --limit 20 --profile <profile>`) and surface any
   recent failures.

Then print a compact table: **check | status (✅/⚠️/❌) | detail**. End with the
single most useful next action (e.g. "run `/databricks:setup` to add a profile").

This is a status check; it only reads, so don't run anything that changes state.
