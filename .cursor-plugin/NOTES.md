# Why `name` is `databricks-skills` here (and `databricks` next door)

The `name` field in this `plugin.json` is intentionally **`databricks-skills`**, not `databricks`, even though the sibling [`../.claude-plugin/plugin.json`](../.claude-plugin/plugin.json) uses `databricks`. This is **not** a typo or stale value — please do not "fix" it.

## Background

This plugin has been published on the Cursor marketplace since at least 2026-02-12 (see [cursor.com/marketplace/databricks](https://cursor.com/marketplace/databricks)). Cursor's marketplace assigned two URL slugs that *look* like they should drive the install identifier:

- `cursor.com/marketplace/databricks` — the plugin landing page
- `cursor.com/marketplace/databricks-apps` — the primary skill's page

…but the **actual install command shown on those pages is `/add-plugin databricks-skills`**. Cursor uses the `name` field from this file as the canonical install identifier — the URL slugs are display-only.

## Why we can't just rename it to `databricks`

Renaming `name` here would change the install identifier Cursor uses to track existing installations under `~/.cursor/plugins/databricks-skills/`. Cursor's update mechanism is undocumented but appears to key on this identifier, so an in-place rename would likely orphan every existing user from auto-updates until they uninstall and reinstall under the new name. Multiple Databricks teams (Field Engineering, Auth Platform, Apps DevEx) have been pointing internal and external customers at the Cursor marketplace listing for months, so the user base is non-trivial.

The Claude Code side has no such constraint — the plugin has never been published to the Anthropic marketplace under any name, so PR #77 freely set the Claude `name` to `databricks` to match the github/gitlab/terraform/linear single-brand-word convention.

## Long-term plan

Tracked as [issue #78](https://github.com/databricks/databricks-agent-skills/issues/78). The right time to rename here is during a Cursor-coordinated major-version bump, with Eric Zakariasson (the Cursor engineer who originally added this manifest in [PR #14](https://github.com/databricks/databricks-agent-skills/pull/14)) confirming the rename either auto-redirects or requires a one-time reinstall on the user side.

## TL;DR for future editors

| File | `name` value | Why |
|------|--------------|-----|
| `.claude-plugin/plugin.json` | `databricks` | Fresh submission, no install-base constraint |
| `.cursor-plugin/plugin.json` | `databricks-skills` | Matches the install ID Cursor users have been using since Feb 2026 |
