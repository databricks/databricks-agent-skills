"""Shared helpers and constants for the skillsgen package (leaf module)."""

import json
from pathlib import Path


# Plugin-level metadata (version, identity, keywords, description, per-target
# shape) is the single source of truth in metaplugin/plugin.meta.json.
# load_meta reads it; the build_* renderers in skillsgen/plugins.py generate
# every target's plugin.json + marketplace.json from it. The skill ->
# plugin-keyword map that used to live here (SKILL_METADATA) now lives in
# metaplugin/plugin.meta.json "skills".
META_FILE = "metaplugin/plugin.meta.json"

# The built bundle every agent fetches (scoped via each catalog's source). The
# four plugin.json live under <BUNDLE_DIR>/<target-dir>/ and the stable skills at
# <BUNDLE_DIR>/skills; the marketplace catalogs at the repo root point a scoped
# source here. Built and drift-checked by skillsgen/bundle.py.
BUNDLE_DIR = "plugins/databricks"

# The release version lives in its own file (NOT in plugin.meta.json) so the
# release workflow can own it and the private mirror can exclude it wholesale
# (a mirror can drop a file, not a single field). load_meta resolves it into
# meta["version"]; require_version fails loud if no version source is available
# where the version is actually used (stamping the per-target plugin.json, and
# the marketplace ref once it pins v{version}).
VERSION_FILE = "metaplugin/version.meta.json"

# Canonical generated plugin.json, read as the version-of-record fallback when
# version.meta.json is absent (e.g. a content regenerate on the mirror side, where
# the version file is excluded): preserving the already-committed version keeps
# such a regenerate from disturbing the released version.
_VERSION_FALLBACK_PLUGIN = f"{BUNDLE_DIR}/claude/.claude-plugin/plugin.json"


def _resolve_version(repo_root: Path) -> str | None:
    """Resolve the release version: version.meta.json (current_version), else the
    version already committed in the canonical plugin.json, else None (in which
    case require_version fails loud at the point the version is needed)."""
    version_path = repo_root / VERSION_FILE
    if version_path.exists():
        return json.loads(version_path.read_text())["current_version"]
    fallback = repo_root / _VERSION_FALLBACK_PLUGIN
    if fallback.exists():
        return json.loads(fallback.read_text()).get("version")
    return None


def load_meta(repo_root: Path) -> dict:
    """Load plugin.meta.json (the cross-target plugin source of truth) and
    resolve the release version into meta["version"] (see _resolve_version)."""
    meta = json.loads((repo_root / META_FILE).read_text())
    version = _resolve_version(repo_root)
    if version is not None:
        meta["version"] = version
    return meta


def require_version(meta: dict) -> str:
    """Return the release version, or fail loud if no version source was found.

    Routed through here at every point that stamps the version into generated
    output, so a generate/validate run with no version source fails with a clear
    message instead of silently emitting a blank or wrong version."""
    version = meta.get("version")
    if not version:
        raise SystemExit(
            f"ERROR: no plugin version available. '{VERSION_FILE}' was not found "
            f"at the repo root (it holds current_version/next_version and is the "
            f"version source for the generated plugin.json), and no committed "
            f"'{_VERSION_FALLBACK_PLUGIN}' was present to fall back to. Restore "
            f"{VERSION_FILE}, or run generation in the public repo where it lives."
        )
    return version


def _serialize_plugin_json(obj: dict) -> str:
    """Canonical on-disk form for a generated plugin JSON file.

    2-space indent, insertion-ordered keys (NOT sorted — each target's key
    order is reproduced by the build_* function), trailing newline.
    """
    return json.dumps(obj, indent=2) + "\n"


def _check_generated_files(repo_root: Path, files: dict) -> list[str]:
    """Fail if any generated file drifts from its expected text.

    Two-stage like validate_manifest: same parsed content but different bytes ->
    a formatting message; different content (or unparseable) -> out-of-date.
    """
    errors: list[str] = []
    for rel, expected in files.items():
        path = repo_root / rel
        if not path.exists():
            errors.append(f"Missing generated file {rel}.")
            continue
        actual = path.read_text()
        if actual == expected:
            continue
        try:
            same_content = json.loads(actual) == json.loads(expected)
        except json.JSONDecodeError:
            same_content = False
        if same_content:
            errors.append(
                f"{rel} is not in canonical generated form (whitespace / key order)."
            )
        else:
            errors.append(f"{rel} is out of date with {META_FILE}.")
    return errors


def _norm_rel_path(path: str) -> str:
    """Normalize a manifest-declared path for comparison ('./x' -> 'x')."""
    path = path.strip()
    while path.startswith("./"):
        path = path[2:]
    return path


def _read_frontmatter(md_path: Path) -> str | None:
    """Return the YAML frontmatter block of a markdown file, or None if absent."""
    text = md_path.read_text()
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]
