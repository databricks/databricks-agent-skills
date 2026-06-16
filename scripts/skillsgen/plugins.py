"""Per-target plugin.json + marketplace.json generation from plugin.meta.json."""

from pathlib import Path

from skillsgen.common import _check_generated_files, _serialize_plugin_json
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


def build_claude_plugin(meta: dict) -> dict:
    return {
        "name": meta["name"],
        "description": meta["description"],
        "version": meta["version"],
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
        "version": meta["version"],
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "keywords": build_keywords(meta),
        "skills": "./skills/",
        "hooks": target["hooks"],
        "interface": target["interface"],
    }


def build_copilot_plugin(meta: dict) -> dict:
    target = meta["targets"]["copilot"]
    return {
        "name": meta["name"],
        "displayName": target["displayName"],
        "description": meta["description"],
        "version": meta["version"],
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "skills": "./skills/",
        "hooks": target["hooks"],
    }


def build_cursor_plugin(meta: dict) -> dict:
    target = meta["targets"]["cursor"]
    # Cursor omits homepage/repository/license and ships the author name only.
    return {
        "name": meta["name"],
        "displayName": target["displayName"],
        "description": meta["description"],
        "version": meta["version"],
        "author": {"name": meta["author"]["name"]},
        "skills": "./skills/",
        "commands": target["commands"],
        "rules": target["rules"],
        "hooks": target["hooks"],
    }


def build_claude_marketplace(meta: dict) -> dict:
    market = meta["marketplace"]
    return {
        "$schema": _CLAUDE_MARKETPLACE_SCHEMA,
        "name": market["name"],
        "description": market["description"],
        "owner": market["owner"],
        "plugins": [
            {
                "name": meta["name"],
                "source": "./",
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


def build_copilot_marketplace(meta: dict) -> dict:
    market = meta["marketplace"]
    return {
        "name": market["name"],
        "description": market["description"],
        "owner": market["owner"],
        "plugins": [
            {
                "name": meta["name"],
                "source": "./",
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


def build_codex_marketplace(meta: dict) -> dict:
    market = meta["marketplace"]
    return {
        "name": market["name"],
        "interface": {"displayName": market["displayName"]},
        "plugins": [
            {
                "name": meta["name"],
                "description": meta["description"],
                "category": meta["category"],
                "source": {"source": "local", "path": "./"},
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
`marketplace.json`) are generated from the repo-root `plugin.meta.json` by
`scripts/skills.py`. To change them, edit `plugin.meta.json` and run
`python3 scripts/skills.py generate`. CI re-renders these files and fails on any
drift, so hand-edits are reverted. See `CONTRIBUTING.md` ("Plugin metadata").
"""

# Directories whose plugin/marketplace JSON is generated; each gets the marker.
_GENERATED_MANIFEST_DIRS = (
    ".claude-plugin",
    ".codex-plugin",
    ".github/plugin",
    ".cursor-plugin",
    ".agents/plugins",
)


def generated_plugin_files(meta: dict) -> dict:
    """Map every generated plugin file (repo-relative path -> canonical text)."""
    files = {
        ".claude-plugin/plugin.json": _serialize_plugin_json(build_claude_plugin(meta)),
        ".codex-plugin/plugin.json": _serialize_plugin_json(build_codex_plugin(meta)),
        ".github/plugin/plugin.json": _serialize_plugin_json(build_copilot_plugin(meta)),
        ".cursor-plugin/plugin.json": _serialize_plugin_json(build_cursor_plugin(meta)),
        ".claude-plugin/marketplace.json": _serialize_plugin_json(
            build_claude_marketplace(meta)
        ),
        ".github/plugin/marketplace.json": _serialize_plugin_json(
            build_copilot_marketplace(meta)
        ),
        ".agents/plugins/marketplace.json": _serialize_plugin_json(
            build_codex_marketplace(meta)
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
            f"Stable skill '{name}' has no entry in plugin.meta.json \"skills\". "
            'Add one with a "keyword" so it gets a plugin keyword.'
        )
    for name in sorted(set(meta_skills) - disk_skills):
        errors.append(
            f"plugin.meta.json \"skills\" lists '{name}' but skills/{name}/ does "
            "not exist. Remove the entry or restore the skill."
        )
    for name, entry in meta_skills.items():
        if not isinstance(entry, dict) or not entry.get("keyword"):
            errors.append(
                f'plugin.meta.json skills["{name}"] is missing a "keyword".'
            )
    return errors


def check_generated_plugins(repo_root: Path, meta: dict) -> list[str]:
    """Fail if any generated plugin file drifts from what meta would produce."""
    return _check_generated_files(repo_root, generated_plugin_files(meta))
