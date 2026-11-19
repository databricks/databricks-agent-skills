---
name: databricks-lakehouse-mcp
description: "Discover, connect to, or recover the hosted Databricks Lakehouse MCP (system.ai.lakehouse), then load its guidance for inspecting, editing, running, and reading results from Databricks notebooks. Use for notebook work in a Databricks workspace or when the user asks to set up the Lakehouse MCP."
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Lakehouse MCP

The hosted `system.ai.lakehouse` service provides notebook tools and the detailed
instructions for using them. This local skill handles discovery and connection;
load operational guidance from the connected service for the user's task.

## Connect or recover

First use the client's tool discovery to look for configured or deferred
Lakehouse MCP tools. If they are available, proceed to skill retrieval.
Otherwise, use the setup instructions shown for `system.ai.lakehouse` in the
user's Databricks workspace to configure and authenticate the connection in
Claude Code or Codex. Use the service's current setup instructions for connection
details; do not guess an endpoint or installer command.

If `system.ai.lakehouse` or its setup instructions are unavailable, or preview
access is denied, direct the user to their Databricks account representative to
establish availability and request access. Installing this skill does not grant
MCP access. Missing tools alone do not show whether the connection is
unconfigured or access is unavailable.

For an authentication error, follow the client's sign-in recovery. For an access
denial, use the relevant access-request path. For a network or service error,
guide retry or diagnosis. If the cause is unclear, keep it unknown. After
explaining a blocker, avoid repeating the same setup prompt on later turns;
continue through an existing supported path when appropriate for the request.

Use `databricks-core` when CLI authentication or profile selection is needed.

## Retrieve the task guidance

1. Discover the connected server's advertised skill tools. Call
   `list_skills(query="<short task keyword>")` to search skill IDs, names, and
   descriptions by case-insensitive substring. Omit `query` to browse the available
   guides, including when a search returns no matches. Follow any returned
   `page_token` to see more results.
2. Load the relevant guide with `load_skill(skill="<returned skill id>")`.
   This returns the full `SKILL.md` instructions and supporting-file metadata.
3. Read the supporting files needed for the task with
   `read_skill_file(skill="<returned skill id>", path="<returned file path>")`.
   Use the exact paths returned by `load_skill` or `list_skill_files`. To browse
   more files, call `list_skill_files(skill="<returned skill id>")`; an optional
   `prefix`, such as `"references/"`, narrows the list. Follow any returned next-call
   instructions to continue browsing with the same filters and `page_token`.
4. Follow the guide and current tool descriptions to perform the task. Load more
   guides when the task requires them, and reuse applicable guidance while it
   remains in context. Refresh the relevant guidance after reconnecting or
   detecting a change in the service's capabilities.

Skill retrieval is a useful connection check; no separate healthcheck is needed.
It verifies access to that read, not permission to edit a notebook or readiness
to run compute. Handle those checks and failures through the relevant operations.
If the server does not advertise skill retrieval, report the missing capability
and use the service's current setup/recovery guidance.
