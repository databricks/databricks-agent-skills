# Plugin hooks

Three hooks make sure Databricks work flows through the skills. All are
stdlib-only Python and **fail open** (any error prints `{}` / no output and
exits 0, so a broken hook never blocks a prompt, session start, or tool call).
`hooks.json` wires them in; Claude Code expands `${CLAUDE_PLUGIN_ROOT}`. Claude
Code auto-loads `hooks/hooks.json`, so it is **not** declared in `plugin.json`
(declaring the standard path double-loads it and fails the plugin).

## `databricks-router.py`: prompt router (UserPromptSubmit)

Runs a fast keyword regex (sub-50ms, no LLM, no network) over each user prompt.
When the prompt is Databricks-related, it injects an `additionalContext`
instruction telling Claude to load `databricks-core` plus the matching product
skill before answering. When it isn't, it prints `{}` and stays out of the way.

The full instruction is injected **once per session** (tracked by a marker file
in the temp dir keyed on the payload's `session_id`); later Databricks prompts
in the same session get a one-line reminder instead, so long sessions don't pay
the full routing block on every turn.

There's no second agent to delegate to. Claude itself drives the `databricks`
CLI through the skills, so "routing" just means "make sure the Databricks skills
are loaded." There is **no permission gating and no cost warning** here.

Precision is tuned to avoid over-routing:

- **STRONG** terms (`databricks`, `unity catalog`, `lakeflow`, `dbfs`,
  `databricks.yml`, `delta live tables`, `genie`, ...) always route, even
  alongside a competitor mention, so "migrate from redshift to databricks"
  routes.
- **AMBIGUOUS** terms (`model serving`, `vector search`, `mlflow`, `pyspark`,
  `medallion`, ...) route only when no **SUPPRESS** term is present.
- **SUPPRESS** terms (competitor platforms + plainly-local dev work like
  `git commit`, `read the file`, `unit test`, `npm`) hold back an ambiguous match.
- **URLs**: code-hosting URLs are blanked before matching, so `databricks`
  appearing only as a GitHub/GitLab org or repo name
  (`github.com/databricks/...`) does not route. URLs whose hostname contains
  `databricks` (workspace and docs hosts) still do.

Edit those three lists when the product surface changes. Behavior is pinned by
`databricks_router_test.py` (`python3 hooks/databricks_router_test.py`).

## `databricks-context.py`: context primer (SessionStart)

Injects a compact banner at session start: the routing rule (load
`databricks-core` + the product skill), CLI presence + version, configured
profile names plus any `[__settings__].default_profile` (parsed from
`~/.databrickscfg` locally, **no network call**, token values never printed),
and whether env/in-platform auth is set. If the CLI isn't installed it points
at `/databricks:setup`.
Covered by `databricks_context_test.py` (`python3 hooks/databricks_context_test.py`).

Its `hooks.json` entry uses `"matcher": "startup|clear|compact"`: the banner
fires for new sessions, `/clear`, and after compaction, but **not on resume**,
where the prior context already contains it.

## `databricks-auth-helper.py`: auth-failure hint (PostToolUse)

Watches Bash tool results (matcher: `Bash`). When a `databricks` command's
output matches a phrase-shaped auth-failure signal (missing default
credentials, `invalid_grant`, `401 unauthorized`, invalid/expired token), it
injects one line suggesting `/databricks:doctor` or `databricks auth login`
before any retry. It never blocks or rewrites tool calls; bare status codes in
ordinary output do not trigger it.
Covered by `databricks_auth_helper_test.py` (`python3 hooks/databricks_auth_helper_test.py`).

## Distribution note

These ship with the Claude Code plugin (the whole repo is the plugin via
`marketplace.json` `source: "./"`). The Databricks CLI install path
(`databricks aitools install`) currently packages **skills only**. See the repo
README for the parity follow-up.
