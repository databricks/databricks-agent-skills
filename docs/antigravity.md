# Databricks plugin for Antigravity

The generated Antigravity package contains all stable Databricks skills, their
reference files, and a native routing rule. It is available for local testing;
runtime validation is pending, and release ZIP assets are not published yet.

## Generate and install locally

From a checkout of this repository, regenerate after editing the source:

```bash
python3 scripts/skills.py generate
python3 scripts/skills.py validate
agy plugin validate ./plugins/databricks/antigravity
agy plugin install ./plugins/databricks/antigravity
agy plugin list --json
```

Use a current Antigravity CLI for `plugin validate`; clean reinstalls require
at least v1.1.28. Confirm `databricks` is enabled and its components include the
stable skills and `databricks-routing` rule. Reload the session if needed.
Invoke `/databricks-core` or ask a Databricks Jobs question to exercise routing.
Follow `databricks-core` for Databricks CLI prerequisites and authentication.

## Update a CLI-managed installation

Regenerate the updated source, validate it, and run `agy plugin install` again
with the generated directory. Keep the plugin name `databricks`, then confirm
the installed version and components with `agy plugin list --json`. Keep the
source directory separate from the managed installation directory.

The CLI [release notes](https://antigravity.google/docs/changelog) document clean
replacement of managed plugin directories from v1.1.28 (September 9, 2026), so
resources deleted from the source do not remain installed. Version 1.3.1
(October 7, 2026) fixed Windows reinstalls while a plugin's MCP servers are
running and prevents marketplace installs from overwriting plugins from a
different source.

The plugin guide lists `install`, `uninstall`, `enable`, `disable`, and `list`;
the changelog also documents `validate`. No separate `update` command is
documented. Uninstall/reinstall is a recovery option.

## Antigravity App and standalone IDE

Place the generated plugin files in `.agents/plugins/databricks/` in your
project or `~/.gemini/config/plugins/databricks/` for all workspaces. The
manifest must be directly at `<plugin-directory>/plugin.json`. Inspect loaded
skills and rules in the agent panel's Customizations menu.

Choose one scope and check for duplicate skills if you previously installed
raw Databricks skills. Replace the plugin directory with a fresh copy when
updating and reload the application. Google's guide does not document a
general Update control for custom directory plugins.

These paths follow Google's [plugin documentation](https://www.antigravity.google/docs/plugins).
The guide promises synchronization of App-installed plugins into CLI;
CLI-to-App synchronization is not established. Discovery and updates still
need runtime verification on each surface.

## Package a local ZIP

After generation and validation, archive the provider directory for transfer:

```bash
python3 scripts/package_antigravity_plugin.py \
  --plugin-root plugins/databricks/antigravity \
  --output /tmp/databricks-antigravity.zip
```

The ZIP has `plugin.json` at its root and includes `LICENSE` and `NOTICE`.
Extract into a fresh directory and run `agy plugin validate <directory>` before
installing. Packaging preserves the generated manifest version.

## Limitations

The package contains skills and routing. Native hooks require Antigravity
adapters: `SessionStart` uses `injectSteps`, no `UserPromptSubmit` event is
documented, and `PostToolUse` documents an empty output object. Installation
through `databricks aitools` needs an adapter in the Databricks CLI repository.

The CLI v1.0.7 release notes announce GitHub subpath installation; that route
needs validation against this provider directory. Marketplace listing follows
Google's separate [submission process](https://www.antigravity.google/docs/marketplace).
