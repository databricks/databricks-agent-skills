"""Structural validation of the on-disk plugin manifests, hooks, and commands."""

import json
import re
from pathlib import Path

from skillsgen.common import _norm_rel_path, _read_frontmatter
from skillsgen.discovery import iter_all_skill_dirs


# ---------------------------------------------------------------------------
# Plugin components (hooks + commands)
# ---------------------------------------------------------------------------
#
# hooks/ and commands/ ship with the Claude Code plugin (the whole repo is the
# plugin via .claude-plugin/marketplace.json `source: "./"`), but they are NOT
# skills, so they live outside the manifest's skills map. These checks keep them
# honest without pulling them into the skill model. Stdlib-only, like the rest
# of this file, so the protected CI runner (no pypi) can run them.

_HOOK_SCRIPT_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?\.py)")


# Documented hook event names per platform. A config keyed on an event outside
# its platform's set silently never fires, which the JSON-validity and
# script-existence checks cannot catch. Verified against each platform's current
# (mid-2026) hooks docs; extend these sets when a platform adds an event we wire.
_CLAUDE_EVENTS = frozenset({
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "Notification",
    "Stop", "SubagentStop", "SessionStart", "SessionEnd", "PreCompact",
})
_CODEX_EVENTS = frozenset({
    "PreToolUse", "PermissionRequest", "PostToolUse", "PreCompact",
    "PostCompact", "UserPromptSubmit", "SubagentStart", "SubagentStop",
    "Stop", "SessionStart",
})
_CURSOR_EVENTS = frozenset({
    "sessionStart", "sessionEnd", "preToolUse", "postToolUse",
    "postToolUseFailure", "subagentStart", "subagentStop",
    "beforeShellExecution", "afterShellExecution", "beforeMCPExecution",
    "afterMCPExecution", "beforeReadFile", "afterFileEdit",
    "beforeSubmitPrompt", "preCompact", "stop", "afterAgentResponse",
    "afterAgentThought", "beforeTabFileRead", "afterTabFileEdit",
    "workspaceOpen",
})
# Copilot accepts its native camelCase events and the PascalCase
# (Claude / Open Plugins) dialect; both are valid.
_COPILOT_EVENTS = frozenset({
    "sessionStart", "sessionEnd", "userPromptSubmitted", "preToolUse",
    "postToolUse", "agentStop", "subagentStop", "errorOccurred",
    "SessionStart", "PreToolUse", "PostToolUse", "UserPromptSubmit",
    "PreCompact", "SubagentStart", "SubagentStop", "Stop",
})


def _check_hook_event_names(rel: str, cfg: dict | None, valid: frozenset, errors: list[str]) -> None:
    """Flag any hook event key in cfg that the platform does not actually fire."""
    if not isinstance(cfg, dict):
        return
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in hooks:
        if event not in valid:
            errors.append(
                f"{rel} wires hook event '{event}', not a documented event for "
                "this platform (it would silently never fire). Valid events: "
                f"{', '.join(sorted(valid))}."
            )


def check_plugin_components(repo_root: Path) -> list[str]:
    """Validate the non-skill plugin components: hooks/ and commands/.

    - plugin.json must NOT declare "hooks": the standard hooks/hooks.json is
      auto-loaded by Claude Code, so declaring it double-loads (a load error)
    - plugin.json MUST declare "commands" when commands/ exists (this repo ships
      commands via that manifest declaration)
    - hooks/hooks.json must be valid JSON, and every ${CLAUDE_PLUGIN_ROOT}/*.py
      script it references must exist
    - every commands/*.md must have frontmatter carrying a `description`, and
      the description must not contain an unquoted ':' (strict YAML parsers
      reject it even though some frontmatter readers tolerate it)

    Returns a list of error strings (empty means all good).
    """
    errors: list[str] = []

    plugin_path = repo_root / ".claude-plugin" / "plugin.json"
    try:
        plugin = json.loads(plugin_path.read_text()) if plugin_path.exists() else {}
    except json.JSONDecodeError as exc:
        # check_generated_plugins reports the broken manifest itself; never
        # crash here, just skip the manifest-dependent checks.
        return [f".claude-plugin/plugin.json is not valid JSON: {exc}"]

    commands_dir = repo_root / "commands"
    if commands_dir.is_dir():
        if "commands" not in plugin:
            errors.append(
                'commands/ exists but .claude-plugin/plugin.json does not declare '
                '"commands": "./commands/". Add it, or the commands silently stop '
                "shipping."
            )
        md_files = sorted(commands_dir.glob("*.md"))
        if not md_files:
            errors.append("commands/ exists but contains no *.md command files.")
        for md in md_files:
            frontmatter = _read_frontmatter(md)
            if frontmatter is None:
                errors.append(
                    f"Command 'commands/{md.name}' is missing YAML frontmatter."
                )
            elif not re.search(r"^description:\s*\S", frontmatter, re.MULTILINE):
                errors.append(
                    f"Command 'commands/{md.name}' frontmatter is missing a 'description'."
                )
            elif re.search(r"^description:[ \t]*[^\s\"'>|].*:(?:\s|$)", frontmatter, re.MULTILINE):
                errors.append(
                    f"Command 'commands/{md.name}' has an unquoted ':' in its "
                    "description, which strict YAML parsers reject. Quote the "
                    "whole description string."
                )

    hooks_json = repo_root / "hooks" / "hooks.json"
    if hooks_json.exists():
        # Claude Code auto-loads the standard hooks/hooks.json. Declaring that
        # same path in plugin.json double-loads it and fails the plugin with a
        # "Duplicate hooks file" error, so the manifest must NOT reference it.
        declared = plugin.get("hooks", [])
        declared = [declared] if isinstance(declared, str) else declared
        if isinstance(declared, list) and any(
            _norm_rel_path(d) == "hooks/hooks.json"
            for d in declared
            if isinstance(d, str)
        ):
            errors.append(
                'plugin.json must not declare "hooks": "./hooks/hooks.json". The '
                "standard hooks/hooks.json is auto-loaded, so declaring it again "
                'double-loads it. Remove the "hooks" key (reserve manifest.hooks '
                "for additional, non-standard hook files)."
            )
        try:
            hooks_cfg = json.loads(hooks_json.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"hooks/hooks.json is not valid JSON: {exc}")
            hooks_cfg = None
        if hooks_cfg is not None:
            blob = json.dumps(hooks_cfg)
            for rel in sorted(set(_HOOK_SCRIPT_RE.findall(blob))):
                if not (repo_root / rel).exists():
                    errors.append(
                        f"hooks/hooks.json references '{rel}' which does not exist."
                    )
        _check_hook_event_names("hooks/hooks.json", hooks_cfg, _CLAUDE_EVENTS, errors)

    return errors


def check_skill_frontmatter(repo_root: Path) -> list[str]:
    """Flag SKILL.md frontmatter that a strict YAML parser would reject.

    Checked with a regex, not yaml.safe_load, because this package is
    stdlib-only (the protected CI runner has no pypi). The failure that bites in
    practice: an unquoted ':' in `description`, which strict-YAML skill loaders
    read as a mapping separator and silently drop. Skills counterpart to the
    commands check in check_plugin_components.

    Returns a list of error strings (empty means all good).
    """
    errors: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        rel = (skill_dir / "SKILL.md").relative_to(repo_root)
        frontmatter = _read_frontmatter(skill_dir / "SKILL.md")
        if frontmatter is None:
            errors.append(f"Skill '{rel}' is missing YAML frontmatter.")
        elif not re.search(r"^description:\s*\S", frontmatter, re.MULTILINE):
            errors.append(f"Skill '{rel}' frontmatter is missing a 'description'.")
        elif re.search(r"^description:[ \t]*[^\s\"'>|].*:(?:\s|$)", frontmatter, re.MULTILINE):
            errors.append(
                f"Skill '{rel}' has an unquoted ':' in its description, which "
                "strict YAML parsers reject (the skill is then silently dropped "
                "at load time). Quote the whole description string."
            )
    return errors


# Any hooks/*.py mentioned in a hooks wiring file, regardless of how the
# platform prefixes the path (${CLAUDE_PLUGIN_ROOT}/, plugin-root-relative, …).
_HOOK_PY_RE = re.compile(r"hooks/[\w.-]+\.py")


def _check_hook_wiring(repo_root: Path, rel: str, errors: list[str]) -> dict | None:
    """Parse a hooks wiring file; verify every hooks/*.py it references exists.

    Returns the parsed config (for caller-specific checks), or None when the
    file is missing or not valid JSON.
    """
    path = repo_root / rel
    if not path.exists():
        errors.append(f"Missing {rel}.")
        return None
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{rel} is not valid JSON: {exc}")
        return None
    for script in sorted(set(_HOOK_PY_RE.findall(json.dumps(cfg)))):
        if not (repo_root / script).exists():
            errors.append(f"{rel} references '{script}' which does not exist.")
    return cfg


def check_cursor_plugin(repo_root: Path) -> list[str]:
    """Validate the Cursor plugin manifest and its hook/command wiring.

    Two Cursor-specific traps this guards:

    - The plugin `name` is the Cursor install identifier. Cursor keys
      installations and updates on it, so changing it orphans every existing
      install from auto-updates without a coordinated Cursor-side migration
      (see .cursor-plugin/NOTES.md).
    - Cursor default-discovers `hooks/hooks.json` (the Claude-format wiring,
      whose event names Cursor cannot parse) when the manifest declares no
      hooks path, so the explicit "hooks" pointer is load-bearing.
    """
    errors: list[str] = []

    plugin_path = repo_root / ".cursor-plugin" / "plugin.json"
    if not plugin_path.exists():
        return [f"Missing {plugin_path.relative_to(repo_root)}"]
    try:
        plugin = json.loads(plugin_path.read_text())
    except json.JSONDecodeError as exc:
        return [f".cursor-plugin/plugin.json is not valid JSON: {exc}"]

    if plugin.get("name") != "databricks":
        errors.append(
            '.cursor-plugin/plugin.json "name" must stay "databricks": it is the '
            "Cursor marketplace install identifier; changing it orphans every "
            "existing install without a coordinated Cursor-side migration "
            "(see .cursor-plugin/NOTES.md)."
        )

    declared_hooks = plugin.get("hooks")
    declared = _norm_rel_path(declared_hooks) if isinstance(declared_hooks, str) else ""
    if declared == "hooks/hooks.json":
        errors.append(
            '.cursor-plugin/plugin.json "hooks" must not point at hooks/hooks.json '
            "(the Claude Code wiring with Claude event names); Cursor needs "
            "hooks/cursor-hooks.json."
        )
    if (repo_root / "hooks" / "cursor-hooks.json").exists():
        if declared != "hooks/cursor-hooks.json":
            errors.append(
                "hooks/cursor-hooks.json exists but .cursor-plugin/plugin.json does "
                'not declare "hooks": "./hooks/cursor-hooks.json". Without the '
                "explicit pointer Cursor default-discovers the Claude-format "
                "hooks/hooks.json and the hooks break."
            )
        cfg = _check_hook_wiring(repo_root, "hooks/cursor-hooks.json", errors)
        if cfg is not None and cfg.get("version") != 1:
            errors.append('hooks/cursor-hooks.json must declare "version": 1.')
        _check_hook_event_names("hooks/cursor-hooks.json", cfg, _CURSOR_EVENTS, errors)

    commands_rel = plugin.get("commands")
    if isinstance(commands_rel, str):
        commands_dir = repo_root / _norm_rel_path(commands_rel)
        md_files = sorted(commands_dir.glob("*.md")) if commands_dir.is_dir() else []
        if not md_files:
            errors.append(
                f'.cursor-plugin/plugin.json declares commands at "{commands_rel}" '
                "but no *.md command files exist there."
            )
        for md in md_files:
            frontmatter = _read_frontmatter(md)
            if frontmatter is None or not re.search(
                r"^description:\s*\S", frontmatter, re.MULTILINE
            ):
                errors.append(
                    f"Cursor command '{md.relative_to(repo_root)}' needs frontmatter "
                    "with a 'description'."
                )

    rules_rel = plugin.get("rules")
    if isinstance(rules_rel, str):
        rules_dir = repo_root / _norm_rel_path(rules_rel)
        mdc_files = sorted(rules_dir.glob("*.mdc")) if rules_dir.is_dir() else []
        if not mdc_files:
            errors.append(
                f'.cursor-plugin/plugin.json declares rules at "{rules_rel}" but no '
                "*.mdc rule files exist there."
            )
        for mdc in mdc_files:
            frontmatter = _read_frontmatter(mdc)
            if frontmatter is None or not re.search(
                r"^description:\s*\S", frontmatter, re.MULTILINE
            ):
                errors.append(
                    f"Cursor rule '{mdc.relative_to(repo_root)}' needs frontmatter "
                    "with a 'description' (Apply-Intelligently rules trigger on it)."
                )

    return errors


def check_codex_plugin(repo_root: Path) -> list[str]:
    """Validate the Codex plugin manifest, marketplace catalog, and hook wiring.

    Codex's default plugin hook file is `hooks/hooks.json`, which is this
    repo's Claude Code wiring, so `.codex-plugin/plugin.json` must point
    "hooks" at `hooks/codex-hooks.json` explicitly. The marketplace entry in
    `.agents/plugins/marketplace.json` becomes load-bearing once users install
    from it (same never-remove rule as the Claude marketplace).
    """
    errors: list[str] = []

    plugin_path = repo_root / ".codex-plugin" / "plugin.json"
    if not plugin_path.exists():
        return [f"Missing {plugin_path.relative_to(repo_root)}"]
    try:
        plugin = json.loads(plugin_path.read_text())
    except json.JSONDecodeError as exc:
        return [f".codex-plugin/plugin.json is not valid JSON: {exc}"]

    if plugin.get("name") != "databricks":
        errors.append(
            '.codex-plugin/plugin.json "name" must be "databricks" (the install '
            "identifier; the marketplace entry and install docs key on it)."
        )

    # No Claude-vs-Codex version cross-check: both plugin.json are generated from
    # meta["version"], and check_generated_plugins enforces byte-exact equality
    # against the source, so any version drift is already caught there.

    skills_rel = plugin.get("skills")
    if not isinstance(skills_rel, str) or not (repo_root / _norm_rel_path(skills_rel)).is_dir():
        errors.append(
            '.codex-plugin/plugin.json "skills" must point at an existing directory.'
        )

    hooks_rel = plugin.get("hooks")
    declared = _norm_rel_path(hooks_rel) if isinstance(hooks_rel, str) else ""
    if declared != "hooks/codex-hooks.json":
        errors.append(
            '.codex-plugin/plugin.json must declare "hooks": "./hooks/codex-hooks.json". '
            "Without it Codex defaults to hooks/hooks.json, the Claude Code wiring."
        )
    cfg = _check_hook_wiring(repo_root, "hooks/codex-hooks.json", errors)
    _check_hook_event_names("hooks/codex-hooks.json", cfg, _CODEX_EVENTS, errors)

    market_path = repo_root / ".agents" / "plugins" / "marketplace.json"
    if not market_path.exists():
        errors.append(f"Missing {market_path.relative_to(repo_root)}")
    else:
        try:
            market = json.loads(market_path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f".agents/plugins/marketplace.json is not valid JSON: {exc}")
            market = None
        if market is not None and not any(
            p.get("name") == plugin.get("name") for p in market.get("plugins", [])
        ):
            errors.append(
                ".agents/plugins/marketplace.json has no entry for plugin "
                f"'{plugin.get('name')}'."
            )

    return errors


def check_copilot_plugin(repo_root: Path) -> list[str]:
    """Validate the GitHub Copilot plugin manifests and hook wiring.

    Copilot CLI resolves plugin manifests in order (.plugin/, repo root,
    .github/plugin/, .claude-plugin/), so the .github/plugin/ manifest is what
    makes the Copilot install Copilot-native instead of falling back to the
    Claude manifest. Its "hooks" pointer must name the Copilot-format wiring
    (hooks/copilot-hooks.json), not the Claude hooks/hooks.json. The
    marketplace entry becomes load-bearing once users install from it (same
    never-remove rule as the Claude marketplace).
    """
    errors: list[str] = []

    plugin_path = repo_root / ".github" / "plugin" / "plugin.json"
    if not plugin_path.exists():
        return [f"Missing {plugin_path.relative_to(repo_root)}"]
    try:
        plugin = json.loads(plugin_path.read_text())
    except json.JSONDecodeError as exc:
        return [f".github/plugin/plugin.json is not valid JSON: {exc}"]

    if plugin.get("name") != "databricks":
        errors.append(
            '.github/plugin/plugin.json "name" must be "databricks" (the install '
            "identifier; the marketplace entry and install docs key on it)."
        )

    # No Claude-vs-Copilot version cross-check: both plugin.json are generated
    # from meta["version"], and check_generated_plugins enforces byte-exact
    # equality against the source, so any version drift is already caught there.

    skills_rel = plugin.get("skills")
    if not isinstance(skills_rel, str) or not (repo_root / _norm_rel_path(skills_rel)).is_dir():
        errors.append(
            '.github/plugin/plugin.json "skills" must point at an existing directory.'
        )

    hooks_rel = plugin.get("hooks")
    declared = _norm_rel_path(hooks_rel) if isinstance(hooks_rel, str) else ""
    if declared != "hooks/copilot-hooks.json":
        errors.append(
            '.github/plugin/plugin.json must declare "hooks": '
            '"./hooks/copilot-hooks.json" (the Copilot-format wiring); '
            "hooks/hooks.json is the Claude Code wiring."
        )
    cfg = _check_hook_wiring(repo_root, "hooks/copilot-hooks.json", errors)
    if cfg is not None and cfg.get("version") != 1:
        errors.append('hooks/copilot-hooks.json must declare "version": 1.')
    _check_hook_event_names("hooks/copilot-hooks.json", cfg, _COPILOT_EVENTS, errors)

    market_path = repo_root / ".github" / "plugin" / "marketplace.json"
    if not market_path.exists():
        errors.append(f"Missing {market_path.relative_to(repo_root)}")
    else:
        try:
            market = json.loads(market_path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f".github/plugin/marketplace.json is not valid JSON: {exc}")
            market = None
        if market is not None and not any(
            p.get("name") == plugin.get("name") for p in market.get("plugins", [])
        ):
            errors.append(
                ".github/plugin/marketplace.json has no entry for plugin "
                f"'{plugin.get('name')}'."
            )

    return errors


# ---------------------------------------------------------------------------
# Routing tables (prompt router + Cursor rule, kept in sync with the skills)
# ---------------------------------------------------------------------------

def _routing_skill_refs(text: str) -> set:
    """The set of databricks-* skill names referenced in a routing table."""
    return set(re.findall(r"databricks-[a-z][a-z0-9-]*", text))


def _load_routing_instruction(repo_root: Path) -> str | None:
    """ROUTING_INSTRUCTION from hooks/databricks-router.py (hyphenated -> load by path)."""
    path = repo_root / "hooks" / "databricks-router.py"
    if not path.exists():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("databricks_router", path)
    if spec is None or spec.loader is None:
        return None
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        return None
    return getattr(module, "ROUTING_INSTRUCTION", None)


def check_routing_tables(repo_root: Path) -> list[str]:
    """Keep the prompt router's and Cursor rule's product-skill tables honest.

    - Every databricks-* skill the router names must exist as a shipped skill; a
      rename or removal otherwise silently points routing at a dead skill.
    - The Cursor routing rule (rules/databricks-routing.mdc), if present, must
      name the same skill set as the router, so the two hand-maintained tables
      cannot drift apart (the router runs on Claude/Codex, the rule on Cursor).
    """
    errors: list[str] = []
    instruction = _load_routing_instruction(repo_root)
    if not instruction:
        # No router (or unreadable) -> nothing to cross-check here.
        return errors

    def _exists(name: str) -> bool:
        return (repo_root / "skills" / name).is_dir() or (
            repo_root / "experimental" / name
        ).is_dir()

    router_refs = _routing_skill_refs(instruction)
    for name in sorted(router_refs):
        if not _exists(name):
            errors.append(
                f"hooks/databricks-router.py routes to '{name}', which is not a "
                "shipped skill under skills/ or experimental/."
            )

    rule_path = repo_root / "rules" / "databricks-routing.mdc"
    if rule_path.exists():
        rule_refs = _routing_skill_refs(rule_path.read_text())
        missing = router_refs - rule_refs
        extra = rule_refs - router_refs
        if missing:
            errors.append(
                "rules/databricks-routing.mdc is missing skills the router routes "
                f"to ({', '.join(sorted(missing))}); keep the Cursor rule's table "
                "in sync with hooks/databricks-router.py."
            )
        if extra:
            errors.append(
                "rules/databricks-routing.mdc routes to skills the router does not "
                f"({', '.join(sorted(extra))}); keep the two routing tables in sync."
            )
    return errors
