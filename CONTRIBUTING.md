## Skill anatomy

Every skill — stable (`skills/<name>/`) or experimental (`experimental/<name>/`) — ships the same set of files:

```
<name>/
├── SKILL.md                         # required: skill prose + frontmatter
├── references/*.md                  # optional: supporting reference content
├── agents/openai.yaml               # required: Codex marketplace metadata
└── assets/
    ├── databricks.svg               # required: icon (Codex marketplace)
    └── databricks.png               # required: icon (Codex marketplace)
```

**`SKILL.md`** is what every coding agent (Claude Code, Cursor, Codex CLI, OpenCode, Copilot, Antigravity) reads. Frontmatter carries `name`, `description`, and optional `metadata.version` + `parent`.

**`agents/openai.yaml`** is Codex CLI's plugin-marketplace metadata format: `display_name`, `short_description`, `icon_small`, `icon_large`, `brand_color`, `default_prompt`. It controls how the skill renders in Codex's in-app marketplace. Other agents ignore this file. The repo ships it for every skill so the manifest is a single feed for all agents.

**`assets/databricks.{svg,png}`** are the icons referenced by `agents/openai.yaml`'s `icon_small` / `icon_large`. Identical across all skills (the Databricks logo); `scripts/skills.py` copies them in from the repo-root `/assets/`.

### Adding or updating a skill

`scripts/skills.py generate` (and `sync`) auto-synthesise both `agents/openai.yaml` and the icons for any skill that's missing them. Hand-authored `agents/openai.yaml` is preserved as-is, so you can curate the display name / short description / default prompt before running `generate` — the synthesiser only writes when the file is absent.

If the synthesised display name comes out wrong (e.g. acronyms or product names that get mis-cased by hyphen-titlecasing), add an entry to `DISPLAY_NAME_OVERRIDES` in `scripts/skills.py` rather than hand-authoring the whole `openai.yaml`.

**Workflow for a new skill**:

```bash
# 1. Create the skill directory + SKILL.md (and references/ if needed).
mkdir -p skills/databricks-foo/references
$EDITOR skills/databricks-foo/SKILL.md      # write SKILL.md with frontmatter

# 2. For stable skills only: add the skill to plugin.meta.json "skills"
#    with a "keyword" (this is its Claude/Codex plugin marketplace keyword).

# 3. Generate Codex metadata + icons + manifest in one shot.
python3 scripts/skills.py generate

# 4. Confirm validate passes (this is what CI runs).
python3 scripts/skills.py validate
```

`generate` is idempotent — re-running it never overwrites your `SKILL.md`, `references/`, or hand-edited `agents/openai.yaml`; it only fills in what's missing.

### CI

`.github/workflows/validate-manifest.yml` runs `python3 scripts/skills.py validate` on every PR that touches the skills, the generator, `metaplugin/plugin.meta.json`, any plugin manifest dir (`.claude-plugin/**`, `.github/plugin/**`, `.cursor-plugin/**`, `.agents/**`), the `plugins/**` bundle, `hooks/**`, the command dirs, or `rules/**`. Validation enforces:

- Every skill has `agents/openai.yaml`.
- Every skill ships `assets/databricks.svg` + `assets/databricks.png` byte-identical to the repo-root source.
- `manifest.json` matches what `scripts/skills.py generate` would produce (stable skills' `repo_dir` stays `skills`; the CLI files-channel fetches the root `skills/`).
- Every stable skill has a `plugin.meta.json` "skills" entry (and vice versa).
- Every target's `plugin.json` + each root `marketplace.json` catalog is byte-identical to what the generator produces from `plugin.meta.json` (no drift across the four targets).
- The whole `plugins/databricks/` per-provider bundle matches a fresh build of the source — no missing, stale, hand-edited, or extra file.
- Every catalog source is scoped to its provider subfolder `plugins/databricks/<provider>` (never a whole-repo `"./"`).

If validation fails the error tells you which file is missing or stale; the fix is always `python3 scripts/skills.py generate` and committing the result.

## Plugin metadata (`metaplugin/plugin.meta.json`)

The repo ships one logical plugin to four targets (Claude Code, Codex, Copilot,
Cursor), each with its own marketplace catalog. All cross-target plugin
metadata, version, name, description, author, license, keywords, per-target
display names, the scoped-source config (`marketplace.source`), and
hook/command/rule wiring, lives once in **`metaplugin/plugin.meta.json`**.
`scripts/skills.py generate` renders it into a **per-provider** bundle under
`plugins/databricks/<provider>/` and the four root catalogs, each pointing a
scoped source at *its own* provider subfolder (`ref: main`):

- per-provider bundles (each self-contained, only what that provider uses):
  - `plugins/databricks/claude/`   — `.claude-plugin/plugin.json` + `skills/` + `commands/` + `hooks/`
  - `plugins/databricks/codex/`    — `.codex-plugin/plugin.json` + `skills/` + `hooks/` + `assets/`
  - `plugins/databricks/copilot/`  — `.github/plugin/plugin.json` + `skills/` + `hooks/`
  - `plugins/databricks/cursor/`   — `.cursor-plugin/plugin.json` + `skills/` + `commands/` + `rules/` + `hooks/`
- root catalogs: `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json`,
  `.agents/plugins/marketplace.json`, `.cursor-plugin/marketplace.json`

**Edit `metaplugin/plugin.meta.json`, then run `python3 scripts/skills.py generate`.** Never
hand-edit the generated files; CI re-renders them in memory and fails on any byte
drift. (The generated JSON carries no "do-not-edit" comment key because the
plugin loaders / the Claude marketplace `$schema` reject unknown keys; their
generated status is documented here and enforced by the drift check.)

The generator lives in `scripts/skillsgen/` (a package split by concern);
`scripts/skills.py` is a thin façade that re-exports its API and is the CLI entry
point. To change or add a *hook* specifically, see `hooks/README.md`
("Changing or adding a hook") — the hook scripts are shared and hand-written,
the per-target wiring JSON is generated.

The plugin keyword list is composed as `keywords_lead + [each skill's keyword] +
keywords_tail`, in the insertion order of the `skills` map. The plugin `name` is
`databricks` for every target and is load-bearing (it keys Cursor/Claude
installs); the generator never emits a different value.

The `routing` block in `plugin.meta.json` is also generated output: the
product-skill table there is rendered into both the prompt router's data
(`hooks/_routing_data.json`, which `hooks/databricks-router.py` loads) and the
Cursor rule (`rules/databricks-routing.mdc`), so the two routing tables cannot
drift. Add a product skill and CI fails until it has a `routing.table` row.
Regenerate the same way: edit `metaplugin/plugin.meta.json`, run `scripts/skills.py generate`.

The four hook-wiring files (`hooks/hooks.json`, `codex-hooks.json`,
`copilot-hooks.json`, `cursor-hooks.json`) are generated from the `hooks` block
+ each target's `hooks_render` (the same three logical hooks rendered into each
runtime's dialect). Edit `metaplugin/plugin.meta.json` and regenerate; only the wiring JSON
is generated, the hook `*.py` scripts are hand-written.

## Plugin components (hooks + commands)

The Claude Code plugin ships more than skills:

- `hooks/`: `hooks.json` wires a UserPromptSubmit prompt router
  (`databricks-router.py`) that steers Databricks-related prompts into the
  skills, a SessionStart context primer (`databricks-context.py`), and a
  PostToolUse auth-failure hinter (`databricks-auth-helper.py`). All
  stdlib-only and fail-open. See [`hooks/README.md`](./hooks/README.md). Each
  hook's behavior is pinned by its matching `tests/*_test.py` file; run the
  suite with `python3 -m unittest discover -s tests -p '*_test.py'`.
  **`hooks/hooks.json` is auto-loaded by Claude Code, so do NOT add a `"hooks"`
  key to `.claude-plugin/plugin.json`, or the plugin fails to load with a
  "Duplicate hooks file" error.**
- `commands/`: one **templated** `*.md` per slash command — the single source
  for both the Claude/Codex form (`/databricks:<name>`) and the Cursor form
  (`/databricks-<name>`). The two differ in frontmatter, `$1`-vs-prose argument
  phrasing, and `:`-vs-`-` namespacing, so the source uses an inline
  `{{ claude-or-codex text | cursor text }}` alternation. `generate` renders each
  provider's command file into its bundle folder (`plugins/databricks/claude/commands/<name>.md`,
  `plugins/databricks/cursor/commands/databricks-<name>.md`). Codex and Copilot
  ship no commands. Edit the template, not the rendered output.

`scripts/skills.py validate` (run in CI) checks that `hooks/hooks.json` is valid
JSON referencing scripts that exist, that plugin.json does not double-declare the
standard hooks file, and that every command carries a `description` (quoted if it
contains a `:`, since strict YAML rejects unquoted colons). The validate
workflow also runs all hook test files.

These components ship via the plugin marketplace inside the `plugins/databricks/`
bundle (each catalog points a scoped source at it, so an install fetches only
that subdir). `databricks aitools install` packages `skills/` only today;
extending it to hooks/commands is CLI-side follow-up work.

## Security

Please see [SECURITY](./SECURITY) for vulnerability reporting guidelines.

## Documentation Safety

Examples in skills and references must follow secure defaults:

- Use least-privilege permissions — don't suggest `ALL PRIVILEGES` when a narrower grant suffices
- If an example requires elevated permissions, state it explicitly (e.g. "requires workspace admin")
- Prefer scoped tokens over broad credentials
- Obfuscate sensitive values: use placeholder workspace IDs (`1111111111111111`), URLs (`company-workspace.cloud.databricks.com`), and never include real tokens or passwords

## Releasing

The release version lives in **`metaplugin/version.meta.json`** (a sibling of
`plugin.meta.json`), so the release workflow owns it and it is managed
automatically:

```json
{ "current_version": "0.2.6", "next_version": "0.2.7" }
```

`current_version` is the latest published release; `next_version` is what the
next release will tag.

### Cutting a release

Run the **Release** workflow (`.github/workflows/release.yml`) via manual
dispatch (it takes no inputs). It:

1. Reads `next_version` from `version.meta.json` as the version to release, and
   aborts if that tag already exists (a stale `next_version`).
2. Runs `scripts/bump_version.py`, which regenerates every target's `plugin.json`,
   the four `marketplace.json` catalogs, `manifest.json`, the routing/hook wiring,
   and the `plugins/databricks/` bundle stamped with the release version, then
   advances `version.meta.json` (`current_version` becomes the released version;
   `next_version` is bumped to the next patch).
3. Validates the regenerated tree, commits it to `main` as the DECO-SDK-Tagging
   App (on the ruleset bypass list), creates the annotated `vX.Y.Z` tag, and cuts
   the GitHub release.

So a release is one dispatch and the version is auto-numbered. To cut a **minor
or major** instead of a patch, set `next_version` in `version.meta.json` (e.g. to
`0.3.0`) first; the workflow releases it and then sets the next patch from there.

### Notes

- **Bumping the `version` is required** for every release: Claude Code's plugin
  marketplace keys updates on the `version` field in `plugin.json`, so a release
  that ships without bumping it leaves marketplace clients on the cached copy.
  That is why the bumped version is committed to `main` (in `version.meta.json`
  and the four `plugin.json`).
- `version.meta.json` is the version source for generation. `scripts/skills.py
  generate` / `validate` read `current_version` from it; if it is absent they fall
  back to the version already committed in `plugin.json`, and fail loudly if no
  version source is available at all.
- The catalogs track `main` (`ref: main`), so the bundle they serve is whatever
  is committed on `main`; bumping the version does not change which ref installs
  follow. The catalogs are not pinned to release tags by design.
- **If a release half-completes** (committed and tagged, but the GitHub release
  was not created), create it manually (`gh release create vX.Y.Z --verify-tag
  --generate-notes`). Because the bump already advanced `next_version`,
  re-dispatching cuts the next version, not a duplicate.
- After releasing, open a follow-up PR to update
  [`cli-compat.json`](#version-resolution-in-databricks-cli) in the CLI repo so
  `databricks aitools install` resolves to the new version.

## Version resolution in Databricks CLI

The Databricks CLI uses [`cli-compat.json`](https://github.com/databricks/cli/blob/main/internal/build/cli-compat.json)
to determine which Agent Skills version to install for `aitools install`. The manifest maps
CLI versions to compatible Agent Skills versions. It lives in the
[CLI repository](https://github.com/databricks/cli) — see the
[README](https://github.com/databricks/cli/blob/main/internal/build/README.md) for details.

## Developer Certificate of Origin

To contribute to this repository, you must sign off your commits to certify 
that you have the right to contribute the code and that it complies with the 
open source license. The rules are pretty simple, if you can certify the 
content of [DCO](./DCO), then simply add a "Signed-off-by" line to your 
commit message to certify your compliance. Please use your real name as 
pseudonymous/anonymous contributions are not accepted.

```
Signed-off-by: Joe Smith <joe.smith@email.com>
```

If you set your `user.name` and `user.email` git configs, you can sign your 
commit automatically with `git commit -s`:

```
git commit -s -m "Your commit message"
```