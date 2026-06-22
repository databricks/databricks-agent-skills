"""Build and drift-check the per-provider plugin bundles under plugins/databricks/.

Each provider gets its own self-contained, fully generated folder:

    plugins/databricks/
    ├── claude/    .claude-plugin/plugin.json + skills/ + commands/ + hooks/(hooks.json, router+context+auth, _routing_data.json)
    ├── codex/     .codex-plugin/plugin.json  + skills/ + hooks/(codex-hooks.json, router+context+auth, _routing_data.json) + assets/
    ├── copilot/   .github/plugin/plugin.json + skills/ + hooks.json + hooks/(context+auth)
    └── cursor/    .cursor-plugin/plugin.json + skills/ + commands/ + rules/ + hooks/(cursor-hooks.json, context+auth)

Each catalog's scoped source points at one of these subfolders, so an install
fetches only that provider's payload (and only what it actually uses — e.g. no
router script where the router isn't wired, top-level assets only for Codex's
interface logo). It is a copy/transform of the editable source (skills/, the
hook scripts, rules/, assets/) plus this provider's generated plugin.json and
rendered commands. Everything under plugins/ is generated.

The bundle is committed and byte-for-byte drift-checked: a missing, stale,
hand-edited, or extra file fails CI. `.gitattributes` marks plugins/**
linguist-generated. The CLI's raw-skills (files-channel) installer is unaffected
— it keeps fetching the root skills/, so manifest.json's repo_dir stays "skills".
Stdlib-only. Run generate_bundle LAST (it copies the just-generated wiring/rules).
"""

import re
import shutil
from pathlib import Path

from skillsgen.commands import render_command_files
from skillsgen.common import BUNDLE_DIR, _serialize_plugin_json
from skillsgen.plugins import (
    _GENERATED_README,
    build_claude_plugin,
    build_codex_plugin,
    build_copilot_plugin,
    build_cursor_plugin,
)

PROVIDERS = ("claude", "codex", "copilot", "cursor")

# Any hooks/*.py referenced by a wiring file, regardless of env-var prefix.
_HOOK_PY_RE = re.compile(r"hooks/[\w.-]+\.py")
# Router data file the router script loads at runtime; copied only where the
# router is wired (Claude, Codex).
_ROUTING_DATA = "hooks/_routing_data.json"


def _provider_specs() -> dict:
    """Per-provider assembly spec. Manifest dir + hook wiring come from meta.targets."""
    return {
        "claude":  {"plugin": build_claude_plugin,  "commands": True,  "rules": False, "assets": False},
        "codex":   {"plugin": build_codex_plugin,   "commands": False, "rules": False, "assets": True},
        "copilot": {"plugin": build_copilot_plugin, "commands": False, "rules": False, "assets": False},
        "cursor":  {"plugin": build_cursor_plugin,  "commands": True,  "rules": True,  "assets": False},
    }


def _is_noise(rel_parts: tuple) -> bool:
    """Files that must never ship (mirrors discovery.iter_skill_files)."""
    if any(part.startswith(".") for part in rel_parts):
        return True
    if "__pycache__" in rel_parts:
        return True
    return any(part.endswith(".pyc") for part in rel_parts)


def _iter_copy(repo_root: Path, src_dir: str):
    """Yield (abs_path, repo-relative posix path) for files under src_dir."""
    base = repo_root / src_dir
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and not _is_noise(path.relative_to(base).parts):
            yield path, path.relative_to(repo_root).as_posix()


def _provider_hook_files(repo_root: Path, provider: str, wiring_out: str) -> dict:
    """{provider-relative path -> bytes} for a provider's hooks/ subset.

    The wiring JSON is copied from the root generation (named per provider there,
    e.g. hooks/codex-hooks.json, to avoid a root collision). Most providers get
    the wiring as `hooks/hooks.json`, but Copilot-format plugins use root-level
    `hooks.json` (VS Code/Copilot auto-discovery looks there). Plus exactly the
    hook scripts the wiring references, and _routing_data.json only when the
    router is wired.
    """
    files: dict = {}
    wiring_path = repo_root / wiring_out
    wiring_text = wiring_path.read_text()
    wiring_rel = "hooks.json" if provider == "copilot" else "hooks/hooks.json"
    files[wiring_rel] = wiring_path.read_bytes()
    scripts = sorted(set(_HOOK_PY_RE.findall(wiring_text)))
    for script in scripts:
        files[script] = (repo_root / script).read_bytes()
    if any(s.endswith("databricks-router.py") for s in scripts):
        files[_ROUTING_DATA] = (repo_root / _ROUTING_DATA).read_bytes()
    return files


def expected_bundle(repo_root: Path, meta: dict) -> dict:
    """Every file the bundle must contain: repo-relative path -> bytes."""
    specs = _provider_specs()
    expected: dict = {}
    for provider, spec in specs.items():
        target = meta["targets"][provider]
        base = f"{BUNDLE_DIR}/{provider}"
        manifest_dir = target["dir"]

        # Generated plugin.json + the do-not-edit marker.
        expected[f"{base}/{manifest_dir}/plugin.json"] = _serialize_plugin_json(
            spec["plugin"](meta)
        ).encode()
        expected[f"{base}/{manifest_dir}/README.md"] = _GENERATED_README.encode()

        # skills/ (copy of the root source).
        for src_abs, rel in _iter_copy(repo_root, "skills"):
            expected[f"{base}/{rel}"] = src_abs.read_bytes()

        # hooks/: this provider's wiring + referenced scripts (+ routing data).
        for rel, data in _provider_hook_files(repo_root, provider, target["hooks_render"]["out"]).items():
            expected[f"{base}/{rel}"] = data

        # commands/: rendered from the templated source (Claude/Cursor only).
        if spec["commands"]:
            for fname, text in render_command_files(repo_root, provider).items():
                expected[f"{base}/commands/{fname}"] = text.encode()

        # rules/ (Cursor) and assets/ (Codex interface logo): copies of source.
        if spec["rules"]:
            for src_abs, rel in _iter_copy(repo_root, "rules"):
                expected[f"{base}/{rel}"] = src_abs.read_bytes()
        if spec["assets"]:
            for src_abs, rel in _iter_copy(repo_root, "assets"):
                expected[f"{base}/{rel}"] = src_abs.read_bytes()

    return expected


def generate_bundle(repo_root: Path, meta: dict) -> int:
    """(Re)build plugins/databricks/ from source. Returns the file count.

    Wipes the bundle dir first so a removed source file leaves no stale copy.
    Run LAST in `generate`, after the wiring/routing/skill assets are current.
    """
    bundle_root = repo_root / BUNDLE_DIR
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    expected = expected_bundle(repo_root, meta)
    for rel, data in expected.items():
        path = repo_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(expected)


def _iter_disk_bundle_files(repo_root: Path):
    bundle_root = repo_root / BUNDLE_DIR
    if not bundle_root.exists():
        return
    for path in bundle_root.rglob("*"):
        if path.is_file():
            yield path.relative_to(repo_root).as_posix()


def check_generated_bundle(repo_root: Path, meta: dict) -> list[str]:
    """Fail if plugins/databricks/ drifts from a fresh build of the source.

    Catches missing, stale/hand-edited, and extra files (the extra-file check is
    what makes "hand-editing the bundle fails CI" hold for additions too).
    """
    errors: list[str] = []
    expected = expected_bundle(repo_root, meta)
    on_disk = set(_iter_disk_bundle_files(repo_root))

    for rel, data in expected.items():
        path = repo_root / rel
        if not path.exists():
            errors.append(f"Missing generated bundle file {rel}.")
        elif path.read_bytes() != data:
            errors.append(
                f"{rel} is out of date with its source "
                "(run `python3 scripts/skills.py generate`)."
            )

    for rel in sorted(on_disk - set(expected)):
        errors.append(
            f"{rel} is in {BUNDLE_DIR}/ but is not produced by the generator "
            "(stale copy or hand-added file). Run `python3 scripts/skills.py "
            "generate`; edit the source, never the bundle."
        )
    return errors
