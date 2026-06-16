#!/usr/bin/env python3
"""Set the plugin version in plugin.meta.json + regenerate all manifests.

Given a `vX.Y.Z` (or `X.Y.Z`) release version, set the `version` field in
`plugin.meta.json` (the single source of truth), then regenerate every target's
`plugin.json` + `marketplace.json` and `manifest.json` so the released commit
ships a fully consistent set.

Why this exists: Claude Code's plugin marketplace keys updates on the `version`
field in `.claude-plugin/plugin.json`. If a release ships without bumping that
field, marketplace clients keep the cached copy and never see the new skills.
`plugin.meta.json` is the one place the version lives now; this writes it there
and lets the generator propagate it to all four targets, so they can never
diverge.

Run by `.github/workflows/release.yml`. Stdlib-only (no pip), so it runs on the
protected runner that can't reach pypi.org.
"""

import argparse
import re
from pathlib import Path

import skills  # sibling module in scripts/

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Matches the first `"version": "..."` field. plugin.meta.json carries exactly
# one top-level `version` key, so a targeted in-place replacement keeps the
# source file's formatting + comments intact (a load/dump round-trip would
# reflow it). The generated plugin.json files ARE round-tripped by the
# generator, which owns their canonical format.
VERSION_FIELD_RE = re.compile(r'("version"\s*:\s*")[^"]*(")')

META_FILE = Path("plugin.meta.json")


def normalize_version(raw: str) -> str:
    """Strip a leading `v` and validate the result is `X.Y.Z`."""
    version = raw.strip()
    if version.startswith("v"):
        version = version[1:]
    if not SEMVER_RE.match(version):
        raise SystemExit(f"ERROR: version must be vX.Y.Z or X.Y.Z, got {raw!r}")
    return version


def set_version(path: Path, version: str) -> bool:
    """Set the `version` field in a JSON file. Returns True if changed."""
    text = path.read_text()
    # Count matches independently of the rewrite: subn(count=1) caps the
    # returned count at 1, so it can only catch the zero-match case, never a
    # second (e.g. nested) "version" key. findall enforces the documented
    # "exactly one version key" invariant so we never silently bump the wrong
    # one if plugin.meta.json grows nested version-like fields.
    matches = len(VERSION_FIELD_RE.findall(text))
    if matches != 1:
        raise SystemExit(
            f'ERROR: expected exactly one "version" field in {path}, found {matches}'
        )
    new_text = VERSION_FIELD_RE.sub(rf"\g<1>{version}\g<2>", text, count=1)
    if new_text == text:
        return False
    path.write_text(new_text)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, e.g. v0.3.0")
    args = parser.parse_args()

    version = normalize_version(args.version)
    repo_root = Path(__file__).resolve().parent.parent

    meta_path = repo_root / META_FILE
    if not meta_path.exists():
        raise SystemExit(
            f"ERROR: {META_FILE} not found at the repo root. It is the plugin "
            "source of truth and must be committed; did you forget to `git add` it?"
        )
    changed = set_version(meta_path, version)
    print(f"{'set' if changed else 'unchanged'} {META_FILE} -> {version}")

    meta = skills.load_meta(repo_root)
    written = skills.generate_plugins(repo_root, meta)
    print(f"regenerated {written} plugin manifest file(s) from {META_FILE}")

    manifest = skills.generate_manifest(repo_root)
    (repo_root / "manifest.json").write_text(skills.serialize_manifest(manifest))
    print("regenerated manifest.json")


if __name__ == "__main__":
    main()
