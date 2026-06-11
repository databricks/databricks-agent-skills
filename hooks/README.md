# Plugin hooks

Three hooks make sure Databricks work flows through the skills. All are
stdlib-only Python and **fail open** (any error prints `{}` / no output and
exits 0, so a broken hook never blocks a prompt, session start, or tool call).
`hooks.json` wires them in; Claude Code expands `${CLAUDE_PLUGIN_ROOT}`. Claude
Code auto-loads `hooks/hooks.json`, so it is **not** declared in `plugin.json`
(declaring the standard path double-loads it and fails the plugin).

`copilot-hooks.json` wires the GitHub Copilot plugin (declared as `"hooks"` in
`.github/plugin/plugin.json`). It uses PascalCase event names, which selects
Copilot's Claude-compatible payload dialect, so the scripts run unchanged and
emit the Claude output envelope. Only two hooks are wired: the context primer
(`SessionStart`; its injected context is honored in VS Code, while Copilot CLI
and the cloud agent ignore session-start stdout) and the auth hinter
(`PostToolUse`, which injects `additionalContext` on every Copilot surface).
The prompt router is not wired: no Copilot surface lets a prompt-submit hook
inject context, so routing rides on skill descriptions and instruction files.
Each entry carries `bash` and `powershell` command variants per Copilot's hook
format.

Each hook is pinned by a test file in `tests/` at the repo root; run the whole
suite with `python3 -m unittest discover -s tests -p '*_test.py'`.

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
  `databricks.yml`, `spark declarative pipelines`, `delta live tables` (the
  legacy name still routes), ...) always route, even alongside an
  alternative-platform mention, so "migrate from redshift to databricks" routes.
- **AMBIGUOUS** terms (`declarative pipelines`, `model serving`, `vector
  search`, `mlflow`, `pyspark`, `genie`, ...) route only when no **SUPPRESS**
  term is present.
- **SUPPRESS** terms (alternative data platforms, Jenkins, and plainly-local
  dev work like `git commit`, `read the file`, `unit test`, `npm`) hold back an
  ambiguous match.
- **URLs**: code-hosting URLs are blanked before matching, so `databricks`
  appearing only as a GitHub/GitLab org or repo name
  (`github.com/databricks/...`) does not route. URLs whose hostname contains
  `databricks` (workspace and docs hosts) still do.

Edit those three lists when the product surface changes. Behavior is pinned by
`tests/databricks_router_test.py`.

## `databricks-context.py`: context primer (SessionStart)

Injects a compact banner at session start: the routing rule (load
`databricks-core` + the product skill), CLI presence + version, configured
profile names plus any `[__settings__].default_profile` (parsed from
`~/.databrickscfg` locally, **no network call**, token values never printed),
and whether env/in-platform auth is set. If the CLI isn't installed it points
at `/databricks:setup`.
Covered by `tests/databricks_context_test.py`.

Its `hooks.json` entry uses `"matcher": "startup|clear|compact"`: the banner
fires for new sessions, `/clear`, and after compaction, but **not on resume**,
where the prior context already contains it.

## `databricks-auth-helper.py`: auth-failure hint (PostToolUse)

Watches Bash tool results (matcher: `Bash`). When a `databricks` command's
output matches a phrase-shaped auth-failure signal (missing default
credentials, `invalid_grant`, `401 unauthorized`, invalid/expired token), it
injects one line suggesting `/databricks:doctor` or `databricks auth login`
before any retry. It never blocks or rewrites tool calls; bare status codes in
ordinary output do not trigger it. Only commands that actually **invoke** the
`databricks` executable count: `databricks` appearing as a repo path, URL, or
argument (`gh pr view --repo databricks/cli`) does not, since such output can
legitimately quote auth-failure phrases without any auth problem.
Covered by `tests/databricks_auth_helper_test.py`.

## Distribution note

These ship with the Claude Code plugin (the whole repo is the plugin via
`marketplace.json` `source: "./"`) and with the GitHub Copilot plugin (primer +
auth hinter via `copilot-hooks.json`, catalogued in
`.github/plugin/marketplace.json`). The Copilot cloud agent takes no plugins;
it only reads hooks vendored into the target repo's `.github/hooks/`. The
Databricks CLI install path (`databricks aitools install`) currently packages
**skills only**. See the repo README for the parity follow-up.
