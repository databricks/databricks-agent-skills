---
description: Set up Databricks CLI auth: install check, then an OAuth / PAT / service-principal profile, then verify.
argument-hint: "[workspace-url]"
allowed-tools: Bash(databricks:*), Read
---

# Databricks Setup

Guide the user through Databricks CLI authentication. Use the **databricks-core**
skill for the authoritative auth details; this command is the step-by-step
wrapper around it.

1. **CLI present?** `databricks --version`. If it's missing,
   follow the install steps in the databricks-core skill
   (`databricks-cli-install.md`). In sandboxed environments (Cursor, containers),
   print the install command and ask the user to run it in their own terminal.
   Don't try to install into the sandbox.
2. **Existing profiles?** `databricks auth profiles`. Show what's already
   configured. If a working profile exists, ask whether to reuse it or add a new
   one.
3. **Pick an auth method** (ask the user; `$1` may be the workspace URL):
   - **OAuth U2M** (default, interactive):
     `databricks auth login --host <workspace-url> --profile <name>`. Opens a
     browser. Best for laptops.
   - **PAT**: `databricks configure --token --profile <name>`; the user pastes
     a personal access token.
   - **Service principal (M2M)**: client id/secret via profile or env. Use for
     CI/automation; never a personal PAT in CI.
   - **In-platform** (notebook/cluster): `DATABRICKS_HOST`/`DATABRICKS_TOKEN`
     are already injected, so no setup is needed.
4. **Confirm before writing** any profile; auth writes to `~/.databrickscfg`.
5. **Verify**: `databricks current-user me --profile <name>` returns the
   expected user.

Never echo tokens or secrets back. Never auto-select a profile. When done,
suggest `/databricks:doctor` for a full health check.
