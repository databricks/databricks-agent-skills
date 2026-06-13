#!/usr/bin/env python3
"""Bump the plugin manifest versions to a release version + regenerate manifest.

Given a `vX.Y.Z` (or `X.Y.Z`) release version, set the `version` field in every
plugin manifest (`.claude-plugin`, `.cursor-plugin`, `.github/plugin`,
`.codex-plugin`), then regenerate `manifest.json` so the released commit ships
a current manifest.

Why this exists: Claude Code's plugin marketplace keys updates on the `version`
field in `.claude-plugin/plugin.json`. If a release ships without bumping that
field, marketplace clients keep the cached copy and never see the new skills.
This makes the release tag the single source of truth for the plugin version.

Run by `.github/workflows/release.yml`. Stdlib-only (no pip), so it runs on the
protected runner that can't reach pypi.org.
"""

import argparse
import re
from pathlib import Path

import skills  # sibling module in scripts/

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Matches the first `"version": "..."` field. Every manifest carries exactly
# one top-level `version` key, so a targeted in-place replacement keeps the
# diff to a single line and avoids reformatting the JSON (which a load/dump
# round-trip would risk).
VERSION_FIELD_RE = re.compile(r'("version"\s*:\s*")[^"]*(")')

PLUGIN_MANIFESTS = (
    Path(".claude-plugin") / "plugin.json",
    Path(".cursor-plugin") / "plugin.json",
    Path(".github") / "plugin" / "plugin.json",
    Path(".codex-plugin") / "plugin.json",
)


def normalize_version(raw: str) -> str:
    """Strip a leading `v` and validate the result is `X.Y.Z`."""
    version = raw.strip()
    if version.startswith("v"):
        version = version[1:]
    if not SEMVER_RE.match(version):
        raise SystemExit(f"ERROR: version must be vX.Y.Z or X.Y.Z, got {raw!r}")
    return version


def set_version(path: Path, version: str) -> bool:
    """Set the `version` field in a plugin manifest. Returns True if changed."""
    text = path.read_text()
    new_text, count = VERSION_FIELD_RE.subn(rf"\g<1>{version}\g<2>", text, count=1)
    if count != 1:
        raise SystemExit(
            f'ERROR: expected exactly one "version" field in {path}, found {count}'
        )
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

    for rel in PLUGIN_MANIFESTS:
        changed = set_version(repo_root / rel, version)
        print(f"{'set' if changed else 'unchanged'} {rel} -> {version}")

    manifest = skills.generate_manifest(repo_root)
    (repo_root / "manifest.json").write_text(skills.serialize_manifest(manifest))
    print("regenerated manifest.json")


if __name__ == "__main__":
    main()
