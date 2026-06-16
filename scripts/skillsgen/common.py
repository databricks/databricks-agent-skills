"""Shared helpers and constants for the skillsgen package (leaf module)."""

import json
from pathlib import Path


# Plugin-level metadata (version, identity, keywords, description, per-target
# shape) is the single source of truth in plugin.meta.json at the repo root.
# load_meta reads it; the build_* renderers below generate every target's
# plugin.json + marketplace.json from it. The skill -> plugin-keyword map that
# used to live here (SKILL_METADATA) now lives in plugin.meta.json "skills".
META_FILE = "plugin.meta.json"


def load_meta(repo_root: Path) -> dict:
    """Load plugin.meta.json (the cross-target plugin source of truth)."""
    return json.loads((repo_root / META_FILE).read_text())


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
            errors.append(f"{rel} is out of date with plugin.meta.json.")
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
