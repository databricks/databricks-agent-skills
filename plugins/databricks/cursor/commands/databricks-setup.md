---
name: databricks-setup
description: "Set up Databricks CLI auth: install check, then an OAuth / PAT / service-principal profile (workspace or account-level), then verify."
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
3. **Pick an auth method** (ask the user; they may have typed a workspace or account console URL after the command):
   - **OAuth U2M** (default, interactive):
     `databricks auth login --host <workspace-url> --profile <name>`. Opens a
     browser. Best for laptops. If the user doesn't know their workspace URL,
     plain `databricks auth login --profile <name>` opens login.databricks.com
     to sign in and pick a workspace. URLs copied from the browser may carry
     `?w=<workspace-id>` or `account_id=` query params; the CLI accepts them,
     but quote the URL so the shell doesn't interpret the `?`.
   - **Account-level**: when the host is an account console URL
     (`accounts.cloud.databricks.com`, `accounts.azuredatabricks.net`,
     `accounts.gcp.databricks.com`), also pass the account ID:
     `databricks auth login --host <account-url> --account-id <uuid> --profile <name>`.
     Ask for the account ID if it isn't in the URL (it's the UUID shown in the
     account console address bar).
   - **PAT**: `databricks configure --token --profile <name>`; the user pastes
     a personal access token. This command prompts on stdin, so don't run it
     yourself (it hangs without a TTY): ask the user to run it in their own
     terminal, then continue once it's done. The same applies to
     `databricks auth login` when no browser can open (headless or sandboxed
     sessions).
   - **Service principal (M2M)**: client id/secret via profile or env. Use for
     CI/automation; never a personal PAT in CI.
   - **In-platform** (notebook/cluster): `DATABRICKS_HOST`/`DATABRICKS_TOKEN`
     are already injected, so no setup is needed.
4. **Confirm before writing** any profile; auth writes to `~/.databrickscfg`.
5. **Verify**: `databricks current-user me --profile <name>` returns the
   expected user. For account-level profiles, `current-user me` doesn't exist;
   use `databricks auth describe --profile <name>` and check the resolved host
   and account ID.

Never echo tokens or secrets back. Never auto-select a profile. When done,
suggest `/databricks-doctor` for a full health check.
