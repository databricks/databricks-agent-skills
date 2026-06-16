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

`.github/workflows/validate-manifest.yml` runs `python3 scripts/skills.py validate` on every PR that touches the skills, the generator, `plugin.meta.json`, any plugin manifest dir (`.claude-plugin/**`, `.codex-plugin/**`, `.github/plugin/**`, `.cursor-plugin/**`, `.agents/**`), `hooks/**`, the command dirs, or `rules/**`. Validation enforces:

- Every skill has `agents/openai.yaml`.
- Every skill ships `assets/databricks.svg` + `assets/databricks.png` byte-identical to the repo-root source.
- `manifest.json` matches what `scripts/skills.py generate` would produce.
- Every stable skill has a `plugin.meta.json` "skills" entry (and vice versa).
- Every target's `plugin.json` + `marketplace.json` is byte-identical to what the generator produces from `plugin.meta.json` (no drift across the four targets).

If validation fails the error tells you which file is missing or stale; the fix is always `python3 scripts/skills.py generate` and committing the result.

## Plugin metadata (`plugin.meta.json`)

The repo ships one logical plugin to four targets (Claude Code, Codex, Copilot,
Cursor) plus a marketplace catalog for three of them. All cross-target plugin
metadata, version, name, description, author, license, keywords, per-target
display names, and hook/command/rule wiring, lives once in **`plugin.meta.json`**
at the repo root. `scripts/skills.py generate` renders it into every target's
`plugin.json` and `marketplace.json`:

- `.claude-plugin/{plugin,marketplace}.json`
- `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json`
- `.github/plugin/{plugin,marketplace}.json`
- `.cursor-plugin/plugin.json`

**Edit `plugin.meta.json`, then run `python3 scripts/skills.py generate`.** Never
hand-edit the generated files; CI re-renders them in memory and fails on any byte
drift. (The generated JSON carries no "do-not-edit" comment key because the
plugin loaders / the Claude marketplace `$schema` reject unknown keys; their
generated status is documented here and enforced by the drift check.)

The plugin keyword list is composed as `keywords_lead + [each skill's keyword] +
keywords_tail`, in the insertion order of the `skills` map. The plugin `name` is
`databricks` for every target and is load-bearing (it keys Cursor/Claude
installs); the generator never emits a different value.

The `routing` block in `plugin.meta.json` is also generated output: the
product-skill table there is rendered into both the prompt router's data
(`hooks/_routing_data.json`, which `hooks/databricks-router.py` loads) and the
Cursor rule (`rules/databricks-routing.mdc`), so the two routing tables cannot
drift. Add a product skill and CI fails until it has a `routing.table` row.
Regenerate the same way: edit `plugin.meta.json`, run `scripts/skills.py generate`.

The four hook-wiring files (`hooks/hooks.json`, `codex-hooks.json`,
`copilot-hooks.json`, `cursor-hooks.json`) are generated from the `hooks` block
+ each target's `hooks_render` (the same three logical hooks rendered into each
runtime's dialect). Edit `plugin.meta.json` and regenerate; only the wiring JSON
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
- `commands/`: one `*.md` per slash command (`/databricks:<name>`), declared via
  `"commands"` in `.claude-plugin/plugin.json`. Each needs frontmatter
  (`description`, optional `argument-hint`, `allowed-tools`).

`scripts/skills.py validate` (run in CI) checks that `hooks/hooks.json` is valid
JSON referencing scripts that exist, that plugin.json does not double-declare the
standard hooks file, and that every command carries a `description` (quoted if it
contains a `:`, since strict YAML rejects unquoted colons). The validate
workflow also runs all hook test files.

These components ship via the plugin marketplace (the whole repo is the plugin).
`databricks aitools install` packages `skills/` only today; extending it to
hooks/commands is CLI-side follow-up work.

## Security

Please see [SECURITY](./SECURITY) for vulnerability reporting guidelines.

## Documentation Safety

Examples in skills and references must follow secure defaults:

- Use least-privilege permissions — don't suggest `ALL PRIVILEGES` when a narrower grant suffices
- If an example requires elevated permissions, state it explicitly (e.g. "requires workspace admin")
- Prefer scoped tokens over broad credentials
- Obfuscate sensitive values: use placeholder workspace IDs (`1111111111111111`), URLs (`company-workspace.cloud.databricks.com`), and never include real tokens or passwords

## Releasing

Releases are cut by the **Release** workflow (`.github/workflows/release.yml`),
triggered manually (`workflow_dispatch`) with a `vX.Y.Z` tag. The workflow:

1. Runs `scripts/bump_version.py <version>`, which sets the `version` field in
   `plugin.meta.json` (the single source) and regenerates every target's
   `plugin.json` + `marketplace.json` and `manifest.json` from it, so all four
   targets carry the same version.
2. Commits the bump (`plugin.meta.json` + the regenerated manifests) to `main`.
3. Creates an annotated `vX.Y.Z` tag (`git tag -a`) at that commit, pushes it,
   then creates the GitHub release (`gh release create --verify-tag`).

Bumping the plugin `version` on every release is **required**: Claude Code's
plugin marketplace keys updates on the `version` field, so a release that ships
without bumping it leaves marketplace clients on the cached copy and they never
see the new skills.

After releasing, open a follow-up PR to update
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