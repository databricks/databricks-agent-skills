"""Per-target plugin.json + marketplace.json generation from plugin.meta.json."""

from pathlib import Path

from skillsgen.common import (
    META_FILE,
    require_version,
    _check_generated_files,
    _norm_rel_path,
    _serialize_plugin_json,
)
from skillsgen.discovery import iter_skill_dirs


# ---------------------------------------------------------------------------
# Plugin manifests (generated from plugin.meta.json for every target)
# ---------------------------------------------------------------------------
#
# One logical plugin ships to four targets (Claude Code, Codex, Copilot,
# Cursor) plus a marketplace catalog for three of them. Every target used to
# keep a hand-edited copy of the same plugin-level metadata (version,
# description, keywords, author, ...) and they drifted: version duplicated 4x,
# Codex missing the app-design keyword, Cursor's description stale. plugin.meta.json
# is now the single source; the build_* renderers below assemble each target's
# file from it in that target's exact key order, and check_generated_plugins
# fails CI on any drift. Stdlib-only, like the rest of this file.
#
# These JSON files are consumed by strict plugin loaders / a JSON-schema
# validator (the Claude marketplace `$schema`), so they carry NO "//" comment
# key (unlike manifest.json, whose consumer tolerates it). Their generated
# status is documented in CONTRIBUTING.md and enforced by the drift check.

_CLAUDE_MARKETPLACE_SCHEMA = (
    "https://json.schemastore.org/claude-code-plugin-marketplace.json"
)


def build_keywords(meta: dict) -> list[str]:
    """Compose the plugin keyword list from meta.

    keywords = keywords_lead + [each skill's keyword, in meta order] +
    keywords_tail. The lead/tail hold cross-cutting terms owned by no single
    skill ("databricks", "data-engineering"); the middle is one keyword per
    shipped skill, ordered by the insertion order of meta["skills"].
    """
    skill_keywords = [entry["keyword"] for entry in meta["skills"].values()]
    return [
        *meta.get("keywords_lead", []),
        *skill_keywords,
        *meta.get("keywords_tail", []),
    ]


# No plugin.json declares a "hooks" path. Each per-provider bundle folder ships
# its wiring as hooks/hooks.json (in that provider's dialect), which every agent
# auto-discovers from the plugin root. Declaring it would double-load (Claude
# fails outright; the others auto-discover the same file). The shared layout
# needed per-provider names (codex-hooks.json, ...) only because hooks/hooks.json
# there was the Claude wiring; per-provider folders remove that conflict.


def build_claude_plugin(meta: dict) -> dict:
    return {
        "name": meta["name"],
        "description": meta["description"],
        "version": require_version(meta),
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "keywords": build_keywords(meta),
        "skills": "./skills/",
        "commands": meta["targets"]["claude"]["commands"],
    }


def build_codex_plugin(meta: dict) -> dict:
    target = meta["targets"]["codex"]
    return {
        "name": meta["name"],
        "description": meta["description"],
        "version": require_version(meta),
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "keywords": build_keywords(meta),
        "skills": "./skills/",
        "interface": target["interface"],
    }


def build_copilot_plugin(meta: dict) -> dict:
    target = meta["targets"]["copilot"]
    return {
        "name": meta["name"],
        "displayName": target["displayName"],
        "description": meta["description"],
        "version": require_version(meta),
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "skills": "./skills/",
    }


def build_cursor_plugin(meta: dict) -> dict:
    target = meta["targets"]["cursor"]
    # Cursor omits homepage/repository/license and ships the author name only.
    return {
        "name": meta["name"],
        "displayName": target["displayName"],
        "description": meta["description"],
        "version": require_version(meta),
        "author": {"name": meta["author"]["name"]},
        "skills": "./skills/",
        "commands": target["commands"],
        "rules": target["rules"],
    }


# ---------------------------------------------------------------------------
# Marketplace catalogs (one per target, at the repo root) + their scoped source
# ---------------------------------------------------------------------------
#
# Each catalog points a *scoped* source at the built bundle (meta.marketplace.
# source.subdir, i.e. plugins/databricks). The four plugin.json live under that
# subdir, so an install fetches only the subdir (a sparse/partial clone), not
# the whole repo: that is what makes the fetch cheap and dodges the Copilot
# fsmonitor crash and the Codex root-source bug. The three ref-capable tools
# (Claude, Codex, Copilot) pin the release tag (ref_template stamped with the
# version), so installs serve a frozen release. Cursor cannot pin a ref, so its
# entry carries the bare relative subdir and tracks the default branch, where
# the bundle is release-frozen.


def marketplace_ref(meta: dict) -> str:
    """The git ref each ref-capable catalog pins: ``main`` today, or the release
    tag (e.g. ``v0.3.0``) once ref_template flips to ``v{version}``. Only the
    latter consumes the version, so resolve it lazily and don't require a version
    source when the ref does not interpolate one."""
    template = meta["marketplace"]["source"]["ref_template"]
    if "{version}" in template:
        return template.format(version=require_version(meta))
    return template


def _scoped_sources(meta: dict) -> dict:
    """Per-target marketplace ``source`` objects, each scoped to that provider's
    bundle subfolder (plugins/databricks/<provider>). An install fetches only its
    own provider's payload."""
    src = meta["marketplace"]["source"]
    subdir = src["subdir"]
    ref = marketplace_ref(meta)

    def path(provider: str) -> str:
        return f"{subdir}/{provider}"

    return {
        # git-subdir does a sparse partial clone of just `path`.
        "claude": {"source": "git-subdir", "url": src["repo"], "path": path("claude"), "ref": ref},
        "copilot": {"source": "github", "repo": src["repo"], "path": path("copilot"), "ref": ref},
        "codex": {"source": "git-subdir", "url": src["git_url"], "path": path("codex"), "ref": ref},
        # Cursor: bare relative subdir, no ref (its index tracks the default branch).
        "cursor": path("cursor"),
    }


def build_claude_marketplace(meta: dict) -> dict:
    return {
        "$schema": _CLAUDE_MARKETPLACE_SCHEMA,
        "name": meta["marketplace"]["name"],
        "description": meta["marketplace"]["description"],
        "owner": meta["marketplace"]["owner"],
        "plugins": [
            {
                "name": meta["name"],
                "source": _scoped_sources(meta)["claude"],
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


def build_copilot_marketplace(meta: dict) -> dict:
    return {
        "name": meta["marketplace"]["name"],
        "description": meta["marketplace"]["description"],
        "owner": meta["marketplace"]["owner"],
        "plugins": [
            {
                "name": meta["name"],
                "source": _scoped_sources(meta)["copilot"],
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


def build_codex_marketplace(meta: dict) -> dict:
    src = meta["marketplace"]["source"]
    entry = {
        "name": meta["name"],
        "description": meta["description"],
        "category": meta["category"],
        "source": _scoped_sources(meta)["codex"],
    }
    # Codex's git-subdir install of skills+hooks needs a `policy` block; its
    # exact shape is the one pending smoke test (proposal open question), so it
    # is emitted only once meta.marketplace.source.codex_policy is filled in.
    if src.get("codex_policy") is not None:
        entry["policy"] = src["codex_policy"]
    return {
        "name": meta["marketplace"]["name"],
        "interface": {"displayName": meta["marketplace"]["displayName"]},
        "plugins": [entry],
    }


def build_cursor_marketplace(meta: dict) -> dict:
    """NEW root catalog for Cursor (the monorepo pattern: source = the subdir)."""
    return {
        "name": meta["marketplace"]["name"],
        "plugins": [
            {
                "name": meta["name"],
                "source": _scoped_sources(meta)["cursor"],
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


# Marker dropped in every generated-manifest directory. The JSON files
# themselves cannot carry a "do not edit" comment (their loaders / the Claude
# marketplace $schema reject unknown keys), so this sibling README is the
# in-folder signal that the directory is generated. It is part of the generated
# set, so the drift check keeps it present and current.
_GENERATED_README = """\
<!-- GENERATED FILE: do not edit by hand. -->

# Generated plugin manifests

The plugin manifest files in this directory (`plugin.json` and/or
`marketplace.json`) are generated from `metaplugin/plugin.meta.json` by
`scripts/skills.py`. To change them, edit `metaplugin/plugin.meta.json` and run
`python3 scripts/skills.py generate`. CI re-renders these files and fails on any
drift, so hand-edits are reverted. See `CONTRIBUTING.md` ("Plugin metadata").
"""

# Root-level directories whose marketplace catalog is generated; each gets the
# marker. The four plugin.json no longer live at the root — they are generated
# into the bundle (plugins/databricks/<target-dir>/) by skillsgen.bundle. The
# root keeps only the per-target marketplace.json catalogs (Cursor's is new).
_GENERATED_MANIFEST_DIRS = (
    ".claude-plugin",
    ".github/plugin",
    ".agents/plugins",
    ".cursor-plugin",
)


def generated_plugin_files(meta: dict) -> dict:
    """Map every generated ROOT-level plugin file (repo-relative path -> text).

    Root level = the four marketplace catalogs (one per target) plus the README
    marker in each catalog directory. The plugin.json manifests are part of the
    bundle, owned by skillsgen.bundle.generated_bundle_files.
    """
    files = {
        ".claude-plugin/marketplace.json": _serialize_plugin_json(
            build_claude_marketplace(meta)
        ),
        ".github/plugin/marketplace.json": _serialize_plugin_json(
            build_copilot_marketplace(meta)
        ),
        ".agents/plugins/marketplace.json": _serialize_plugin_json(
            build_codex_marketplace(meta)
        ),
        ".cursor-plugin/marketplace.json": _serialize_plugin_json(
            build_cursor_marketplace(meta)
        ),
    }
    for directory in _GENERATED_MANIFEST_DIRS:
        files[f"{directory}/README.md"] = _GENERATED_README
    return files


def generate_plugins(repo_root: Path, meta: dict) -> int:
    """Write every target's plugin.json + marketplace.json from meta.

    Idempotent: always writes the full set and returns its size.
    """
    files = generated_plugin_files(meta)
    for rel, text in files.items():
        path = repo_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return len(files)


def check_meta_skill_coverage(repo_root: Path, meta: dict) -> list[str]:
    """Every stable skill must have a plugin.meta.json entry, and vice versa.

    This is the coverage guard: add a skill under skills/ and forget to list it
    in plugin.meta.json (so it gets no plugin keyword) and this fails, instead
    of the keyword silently going missing from every target's plugin.json.
    """
    errors: list[str] = []
    meta_skills = meta.get("skills", {})
    disk_skills = {d.name for d in iter_skill_dirs(repo_root)}

    for name in sorted(disk_skills - set(meta_skills)):
        errors.append(
            f"Stable skill '{name}' has no entry in {META_FILE} \"skills\". "
            'Add one with a "keyword" so it gets a plugin keyword.'
        )
    for name in sorted(set(meta_skills) - disk_skills):
        errors.append(
            f"{META_FILE} \"skills\" lists '{name}' but skills/{name}/ does "
            "not exist. Remove the entry or restore the skill."
        )
    for name, entry in meta_skills.items():
        if not isinstance(entry, dict) or not entry.get("keyword"):
            errors.append(
                f'{META_FILE} skills["{name}"] is missing a "keyword".'
            )
    return errors


def check_generated_plugins(repo_root: Path, meta: dict) -> list[str]:
    """Fail if any generated plugin file drifts from what meta would produce."""
    return _check_generated_files(repo_root, generated_plugin_files(meta))


def check_scoped_sources(meta: dict) -> list[str]:
    """Assert every catalog points a scoped source at the bundle, never "./".

    The drift check proves the committed catalogs match the generator; this
    proves the generator itself never regresses to a whole-repo "./" source,
    which would drag the entire tree into every install and reintroduce the
    Copilot fsmonitor crash and the Codex root-source bug the subdir fixes.
    """
    errors: list[str] = []
    subdir = meta["marketplace"]["source"]["subdir"]
    expected = {
        ".claude-plugin/marketplace.json": (build_claude_marketplace(meta), f"{subdir}/claude"),
        ".github/plugin/marketplace.json": (build_copilot_marketplace(meta), f"{subdir}/copilot"),
        ".agents/plugins/marketplace.json": (build_codex_marketplace(meta), f"{subdir}/codex"),
        ".cursor-plugin/marketplace.json": (build_cursor_marketplace(meta), f"{subdir}/cursor"),
    }
    for rel, (catalog, want) in expected.items():
        for plugin in catalog.get("plugins", []):
            src = plugin.get("source")
            path = src if isinstance(src, str) else (src or {}).get("path")
            normalized = _norm_rel_path(path) if isinstance(path, str) else None
            if normalized in ("", "."):
                errors.append(
                    f"{rel} uses a whole-repo source; it must be scoped to "
                    f"{want} (a './' source drags the whole tree into every "
                    "install and reintroduces the Copilot/Codex bugs)."
                )
            elif normalized != want:
                errors.append(
                    f"{rel} source path is {path!r}; expected the provider "
                    f"subfolder {want!r}."
                )
    return errors
