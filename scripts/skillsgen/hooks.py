"""The four hook-wiring dialects, generated from the meta hooks block."""

from pathlib import Path

from skillsgen.common import _check_generated_files, _serialize_plugin_json


# ---------------------------------------------------------------------------
# Hooks (the four hook-wiring dialects, generated from meta "hooks")
# ---------------------------------------------------------------------------
#
# Three logical hooks (router, context, auth) ship to four runtimes whose hook
# wiring formats differ in schema shape, event-name casing, env-var convention,
# command form, and which hooks are wired. The shared content lives once in
# plugin.meta.json "hooks"; the build_* functions below render each target's
# dialect. The router is wired only on Claude + Codex (Copilot/Cursor cannot
# inject context from a prompt-submit hook). Generated event names land in the
# per-platform allow-lists checked by _check_hook_event_names.

def _hook_scripts(meta: dict) -> dict:
    """Map hook id -> script filename from meta."""
    return {entry["id"]: entry["script"] for entry in meta["hooks"]["entries"]}


def _nested_command(env_root: str, script: str) -> str:
    """The 'python3 X || python X || true' fallback chain for Claude/Codex."""
    target = f'"{env_root}/hooks/{script}"'
    return f"python3 {target} || python {target} || true"


def build_nested_hooks(meta: dict, target_key: str) -> dict:
    """Claude / Codex dialect: nested hooks arrays, PascalCase events, the
    env-var-rooted fallback-chain command, router included. Differs between the
    two only in env_root, tool_matcher, and whether the description is present.
    """
    hooks_meta = meta["hooks"]
    render = meta["targets"][target_key]["hooks_render"]
    scripts = _hook_scripts(meta)
    env_root = render["env_root"]

    result: dict = {}
    if render.get("description"):
        result["description"] = hooks_meta["description"]
    result["hooks"] = {
        "UserPromptSubmit": [
            {
                "hooks": [
                    {"type": "command", "command": _nested_command(env_root, scripts["router"])}
                ]
            }
        ],
        "SessionStart": [
            {
                "matcher": hooks_meta["session_start_matcher"],
                "hooks": [
                    {"type": "command", "command": _nested_command(env_root, scripts["context"])}
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": render["tool_matcher"],
                "hooks": [
                    {"type": "command", "command": _nested_command(env_root, scripts["auth"])}
                ],
            }
        ],
    }
    return result


def build_copilot_hooks(meta: dict) -> dict:
    """Copilot dialect: version 1, flat entries with bash/powershell variants,
    PascalCase events, repo-relative paths, no router.
    """
    render = meta["targets"]["copilot"]["hooks_render"]
    scripts = _hook_scripts(meta)

    def entry(script: str, matcher: str | None) -> dict:
        item: dict = {"type": "command"}
        if matcher is not None:
            item["matcher"] = matcher
        item["bash"] = f"python3 hooks/{script}"
        item["powershell"] = f"python hooks/{script}"
        return item

    return {
        "version": 1,
        "hooks": {
            "SessionStart": [entry(scripts["context"], None)],
            "PostToolUse": [entry(scripts["auth"], render["tool_matcher"])],
        },
    }


def build_cursor_hooks(meta: dict) -> dict:
    """Cursor dialect: version 1, flat entries with a single command plus the
    --platform cursor flag, camelCase events, no router.
    """
    render = meta["targets"]["cursor"]["hooks_render"]
    scripts = _hook_scripts(meta)
    flag = render["platform_flag"]

    def entry(script: str, matcher: str | None) -> dict:
        item: dict = {"command": f"python3 hooks/{script} {flag}"}
        if matcher is not None:
            item["matcher"] = matcher
        return item

    return {
        "version": 1,
        "hooks": {
            "sessionStart": [entry(scripts["context"], None)],
            "postToolUse": [entry(scripts["auth"], render["tool_matcher"])],
        },
    }


def generated_hook_files(meta: dict) -> dict:
    """Map the generated hook-wiring files (repo-relative path -> canonical text)."""
    return {
        meta["targets"]["claude"]["hooks_render"]["out"]: _serialize_plugin_json(
            build_nested_hooks(meta, "claude")
        ),
        meta["targets"]["codex"]["hooks_render"]["out"]: _serialize_plugin_json(
            build_nested_hooks(meta, "codex")
        ),
        meta["targets"]["copilot"]["hooks_render"]["out"]: _serialize_plugin_json(
            build_copilot_hooks(meta)
        ),
        meta["targets"]["cursor"]["hooks_render"]["out"]: _serialize_plugin_json(
            build_cursor_hooks(meta)
        ),
    }


def generate_hooks(repo_root: Path, meta: dict) -> int:
    """Write each target's hook-wiring file from meta. Idempotent."""
    files = generated_hook_files(meta)
    for rel, text in files.items():
        path = repo_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return len(files)


def check_generated_hooks(repo_root: Path, meta: dict) -> list[str]:
    """Fail if any generated hook-wiring file drifts from what meta would produce."""
    return _check_generated_files(repo_root, generated_hook_files(meta))


# No hooks/*.py is expected to exist without being wired into meta["hooks"]. Add
# a filename here (with a reason) only if a deliberately-unwired helper script is
# ever introduced.
_UNWIRED_HOOK_SCRIPTS: frozenset = frozenset()


def check_no_orphan_hook_scripts(repo_root: Path, meta: dict) -> list[str]:
    """Every hooks/*.py must be wired into meta["hooks"]["entries"] (or allow-listed).

    The reverse of test_wired_scripts_exist (which checks wired -> exists): this
    checks exists -> wired, so a hook script that is added but never wired into
    any target (dead code that still ships) fails CI instead of riding along
    unnoticed.
    """
    wired = set(_hook_scripts(meta).values()) | set(_UNWIRED_HOOK_SCRIPTS)
    errors: list[str] = []
    for py in sorted((repo_root / "hooks").glob("*.py")):
        if py.name not in wired:
            errors.append(
                f"hooks/{py.name} exists but is not wired into plugin.meta.json "
                '"hooks"."entries" (and is not allow-listed). Wire it or remove it.'
            )
    return errors
