#!/usr/bin/env python3
"""Cut a release version from version.meta.json, then advance it.

The release version lives in `version.meta.json` (NOT plugin.meta.json):

    { "current_version": "0.2.6", "next_version": "0.2.7" }

This script (run by .github/workflows/release.yml on manual dispatch) takes
`next_version` as the version to release, regenerates every target's
`plugin.json` + each `marketplace.json` catalog, `manifest.json`, the
routing/hook wiring, and the `plugins/databricks/` bundle stamped with it, then
advances `version.meta.json` so `current_version` becomes the just-released
version and `next_version` is bumped to the next patch. To cut a minor/major
instead, set `next_version` before dispatching; the next patch is computed from
whatever you set.

Why the version lives in its own file: Claude Code's plugin marketplace keys
updates on the `version` field in `plugin.json`, so every release must bump it.
Keeping it out of `plugin.meta.json` lets the release workflow own it and lets
the private mirror exclude it wholesale (a mirror can drop a file, not a single
field), so publishing never fights the version.

Stdlib-only (no pip), so it runs on the protected runner that can't reach
pypi.org.
"""

import json
import re
from pathlib import Path

import skills  # sibling module in scripts/

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_FILE = Path("metaplugin/version.meta.json")


def _next_patch(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    version_path = repo_root / VERSION_FILE
    if not version_path.exists():
        raise SystemExit(
            f"ERROR: {VERSION_FILE} not found. It is the version source "
            "(current_version/next_version) and must be committed."
        )

    state = json.loads(version_path.read_text())
    release = state["next_version"].strip()
    if not SEMVER_RE.match(release):
        raise SystemExit(f"ERROR: next_version must be X.Y.Z, got {release!r}")

    # Regenerate everything stamped with the release version. load_meta resolves
    # the current (pre-release) version; override meta["version"] with
    # next_version so this build carries the version we are about to tag.
    meta = skills.load_meta(repo_root)
    meta["version"] = release

    written = skills.generate_plugins(repo_root, meta)
    print(f"regenerated {written} plugin manifest file(s) at {release}")

    written_routing = skills.generate_routing(repo_root, meta)
    print(f"regenerated {written_routing} routing file(s)")

    written_hooks = skills.generate_hooks(repo_root, meta)
    print(f"regenerated {written_hooks} hook-wiring file(s)")

    manifest = skills.generate_manifest(repo_root)
    (repo_root / "manifest.json").write_text(skills.serialize_manifest(manifest))
    print("regenerated manifest.json")

    # Last: the bundle copies skills/, hooks/, commands/, rules/, assets/ and the
    # wiring regenerated above, plus the four plugin.json with the release version.
    written_bundle = skills.generate_bundle(repo_root, meta)
    print(f"regenerated {written_bundle} file(s) in the plugins/databricks/ bundle")

    # Advance the version state: the released version becomes current, and
    # next_version is bumped to the next patch. Done last so a failure before
    # here leaves next_version untouched and a re-dispatch retries the same
    # version rather than skipping one.
    state["current_version"] = release
    state["next_version"] = _next_patch(release)
    version_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"advanced {VERSION_FILE}: current={release} next={state['next_version']}")
    print(f"released v{release}")


if __name__ == "__main__":
    main()
