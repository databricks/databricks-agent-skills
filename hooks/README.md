# Plugin hooks

Two hooks make sure Databricks work flows through the skills. Both are
stdlib-only Python and **fail open** (any error prints `{}` / no output and
exits 0, so a broken hook never blocks a prompt or session start). `hooks.json`
wires them in; Claude Code expands `${CLAUDE_PLUGIN_ROOT}`. Claude Code
auto-loads `hooks/hooks.json`, so it is **not** declared in `plugin.json`
(declaring the standard path double-loads it and fails the plugin).

## `databricks-router.py` — prompt router (UserPromptSubmit)

Runs a fast keyword regex (sub-50ms, no LLM, no network) over each user prompt.
When the prompt is Databricks-related, it injects an `additionalContext`
instruction telling Claude to load `databricks-core` plus the matching product
skill before answering. When it isn't, it prints `{}` and stays out of the way.

There's no second agent to delegate to — Claude itself drives the `databricks`
CLI through the skills, so "routing" just means "make sure the Databricks skills
are loaded." There is **no permission gating and no cost warning** here.

Precision is tuned to avoid over-routing:

- **STRONG** terms (`databricks`, `unity catalog`, `lakeflow`, `dbfs`,
  `databricks.yml`, `delta live tables`, `genie`, …) always route — even
  alongside a competitor mention, so "migrate from redshift to databricks"
  routes.
- **AMBIGUOUS** terms (`model serving`, `vector search`, `mlflow`, `pyspark`,
  `medallion`, …) route only when no **SUPPRESS** term is present.
- **SUPPRESS** terms (competitor platforms + plainly-local dev work like
  `git commit`, `read the file`, `unit test`, `npm`) hold back an ambiguous match.

Edit those three lists when the product surface changes. Behavior is pinned by
`databricks_router_test.py` (`python3 hooks/databricks_router_test.py`).

## `databricks-context.py` — context primer (SessionStart)

Injects a compact banner once at session start: the routing rule (load
`databricks-core` + the product skill), CLI presence + version, configured
profile names (parsed from `~/.databrickscfg` locally —
**no network call**, token values never printed), and whether env/in-platform
auth is set. If the CLI isn't installed it points at `/databricks:setup`.

## Distribution note

These ship with the Claude Code plugin (the whole repo is the plugin via
`marketplace.json` `source: "./"`). The Databricks CLI install path
(`databricks aitools install`) currently packages **skills only** — see the repo
README for the parity follow-up.
