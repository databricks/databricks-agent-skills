#!/usr/bin/env python3
"""Manage skills: sync shared assets, generate manifest, validate."""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


SHARED_ASSETS = [
    "assets/databricks.svg",
    "assets/databricks.png",
]

# Stable directory: "skills/<name>/". Experimental: "experimental/<name>/".
# The wire format carries each entry's source directory in `repo_dir`; consumers
# derive experimental state from that. No parallel `experimental_skills` map.
STABLE_REPO_DIR = "skills"
EXPERIMENTAL_REPO_DIR = "experimental"

# Stable-skill -> Claude marketplace plugin keyword. Used by
# check_plugin_manifest to verify .claude-plugin/plugin.json keywords stay
# aligned with the shipped skills. Descriptions live in each skill's SKILL.md
# frontmatter and are synthesized into the manifest via _build_stable_entry.
SKILL_METADATA = {
    "databricks-core": {"plugin_keyword": "cli"},
    "databricks-apps": {"plugin_keyword": "apps"},
    "databricks-app-design": {"plugin_keyword": "app-design"},
    "databricks-jobs": {"plugin_keyword": "jobs"},
    "databricks-lakebase": {"plugin_keyword": "lakebase"},
    "databricks-dabs": {"plugin_keyword": "dabs"},
    "databricks-model-serving": {"plugin_keyword": "model-serving"},
    "databricks-pipelines": {"plugin_keyword": "pipelines"},
    "databricks-serverless-migration": {"plugin_keyword": "serverless"},
    "databricks-vector-search": {"plugin_keyword": "vector-search"},
}


def iter_skill_dirs(repo_root: Path, parent: str = STABLE_REPO_DIR):
    """Yield skill directories under `parent` that contain SKILL.md."""
    skills_dir = repo_root / parent
    if not skills_dir.exists():
        return
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith(".") or item.name == "scripts":
            continue
        if not (item / "SKILL.md").exists():
            continue
        yield item


def iter_experimental_skill_dirs(repo_root: Path):
    """Yield experimental skill directories (under `experimental/`)."""
    yield from iter_skill_dirs(repo_root, parent=EXPERIMENTAL_REPO_DIR)


def extract_version_from_skill(skill_path: Path) -> str:
    """Extract version from SKILL.md frontmatter metadata."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"SKILL.md not found in {skill_path}")

    content = skill_md.read_text()

    if not content.startswith("---"):
        raise ValueError(f"SKILL.md in {skill_path} missing frontmatter")

    end_idx = content.find("---", 3)
    if end_idx == -1:
        raise ValueError(f"SKILL.md in {skill_path} has unclosed frontmatter")

    frontmatter = content[3:end_idx]

    version_match = re.search(r'version:\s*["\']?([^"\'\n]+)["\']?', frontmatter)
    if version_match:
        return version_match.group(1).strip()

    # Floor: skills without an explicit version in SKILL.md frontmatter
    # get 0.0.1 in the manifest. Avoids 0.0.0 which several install tools
    # treat as "unset" rather than "first release".
    return "0.0.1"


def iter_skill_files(skill_path: Path):
    """Yield tracked files in a skill directory, skipping VCS-ignored noise.

    Filters out dot-prefixed paths (.DS_Store, .git, etc.), __pycache__
    directories, and *.pyc files so manifest output stays reproducible
    across machines.
    """
    for file_path in skill_path.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = file_path.relative_to(skill_path).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if "__pycache__" in rel_parts:
            continue
        if file_path.suffix == ".pyc":
            continue
        yield file_path


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def iter_all_skill_dirs(repo_root: Path):
    """Yield every skill directory across stable and experimental."""
    yield from iter_skill_dirs(repo_root, parent=STABLE_REPO_DIR)
    yield from iter_skill_dirs(repo_root, parent=EXPERIMENTAL_REPO_DIR)


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------

_BLOCK_SCALAR_INDICATORS = {"|", "|-", "|+", ">", ">-", ">+"}


def extract_description_from_skill(skill_path: Path) -> str:
    """Best-effort extraction of `description:` from SKILL.md frontmatter.

    Handles plain (`description: foo`), quoted (`description: "foo"`), and
    block-scalar (`description: >-` followed by indented lines) values.
    Stdlib-only to keep the validate workflow on the protected runner
    self-contained — that runner can't reach pypi.org.
    """
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return ""
    content = skill_md.read_text()
    if not content.startswith("---"):
        return ""
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return ""
    lines = content[3:end_idx].splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'^description:\s*(.*?)\s*$', line)
        if not m:
            continue
        value = m.group(1)
        if value in _BLOCK_SCALAR_INDICATORS:
            collected = []
            for cont in lines[i + 1:]:
                if cont and not cont[0].isspace():
                    break
                stripped = cont.strip()
                if stripped:
                    collected.append(stripped)
            joiner = " " if value.startswith(">") else "\n"
            return joiner.join(collected)
        return value.strip().strip('"').strip("'")
    return ""


# Markers that separate the "what this skill does" lead-in from the
# "Use when ..." trigger list. The Codex marketplace short_description should
# only contain the lead-in.
_SHORT_DESC_MARKERS = (". Use when", ". Use this", ". Triggers", ". ALWAYS")


def synthesize_short_description(skill_path: Path) -> str:
    """Derive a short marketplace blurb from the SKILL.md frontmatter."""
    desc = extract_description_from_skill(skill_path)
    for marker in _SHORT_DESC_MARKERS:
        idx = desc.find(marker)
        if idx >= 0:
            desc = desc[:idx] + "."
            break
    if len(desc) > 200:
        desc = desc[:197].rstrip() + "..."
    return desc.strip()


DISPLAY_NAME_OVERRIDES = {
    "databricks-ai-functions": "Databricks AI Functions",
    "databricks-aibi-dashboards": "Databricks AI/BI Dashboards",
    "databricks-mlflow-evaluation": "Databricks MLflow Evaluation",
    "databricks-unstructured-pdf-generation": "Databricks Unstructured PDF Generation",
}


def synthesize_openai_yaml(skill_name: str, short_description: str) -> str:
    """Build the Codex marketplace metadata for an experimental skill."""
    display_name = DISPLAY_NAME_OVERRIDES.get(
        skill_name,
        " ".join(p.capitalize() for p in skill_name.split("-")),
    )
    short = short_description.replace('"', '\\"')
    prompt_blurb = short_description.rstrip(".").lower().replace('"', '\\"')
    return (
        "interface:\n"
        f'  display_name: "{display_name}"\n'
        f'  short_description: "{short}"\n'
        '  icon_small: "./assets/databricks.svg"\n'
        '  icon_large: "./assets/databricks.png"\n'
        '  brand_color: "#FF3621"\n'
        f'  default_prompt: "Use ${skill_name} for {prompt_blurb}."\n'
    )


def ensure_codex_metadata(repo_root: Path) -> int:
    """Ensure every skill has agents/openai.yaml + shared assets.

    Applies uniformly to stable (`skills/`) and experimental (`experimental/`)
    skills:

    - **assets**: copies `assets/databricks.{svg,png}` from the repo root into
      each skill's `assets/` directory. Overwrites stale copies (content mismatch
      against the source) so the bundled icons never drift; preserves source
      mtime via `shutil.copy2` so skill `updated_at` timestamps stay stable.
    - **agents/openai.yaml**: synthesises a Codex marketplace metadata file
      from the SKILL.md frontmatter when one is missing. Hand-authored
      `openai.yaml` is preserved as-is, so skill authors can curate the
      display name / short description / default prompt without their work
      being overwritten on every `generate`.

    Returns the number of files written (assets and openai.yaml combined).

    This is the single source of truth for the "every skill ships icons +
    Codex metadata" contract. `check_codex_metadata` is its validation
    counterpart.
    """
    written = 0
    # Source-of-truth assets at the repo root must exist before we copy
    # anything; surface that as a clean error instead of a per-skill failure.
    for asset_rel in SHARED_ASSETS:
        if not (repo_root / asset_rel).exists():
            raise ValueError(f"Missing shared asset '{asset_rel}' at repo root.")

    for skill_dir in iter_all_skill_dirs(repo_root):
        for asset_rel in SHARED_ASSETS:
            source = repo_root / asset_rel
            dest = skill_dir / asset_rel
            if dest.exists() and dest.read_bytes() == source.read_bytes():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            written += 1

        openai_path = skill_dir / "agents" / "openai.yaml"
        if openai_path.exists():
            continue
        openai_path.parent.mkdir(parents=True, exist_ok=True)
        openai_path.write_text(
            synthesize_openai_yaml(skill_dir.name, synthesize_short_description(skill_dir))
        )
        written += 1
    return written


def check_codex_metadata(repo_root: Path) -> list[str]:
    """Validate every skill has shared assets + agents/openai.yaml.

    Mirror of `ensure_codex_metadata`: each skill must ship the icons
    `assets/databricks.{svg,png}` (byte-identical to the repo-root source)
    and an `agents/openai.yaml` marketplace metadata file. Applies to both
    stable and experimental skills.

    Returns a list of error messages; empty list means everything is in
    order. The CI workflow `validate-manifest.yml` runs this on every PR
    that touches `skills/`, `experimental/`, `assets/`, `scripts/skills.py`,
    or `manifest.json`.
    """
    errors: list[str] = []
    for asset_rel in SHARED_ASSETS:
        if not (repo_root / asset_rel).exists():
            errors.append(f"Missing shared asset '{asset_rel}' at repo root.")
    if errors:
        return errors

    for skill_dir in iter_all_skill_dirs(repo_root):
        for asset_rel in SHARED_ASSETS:
            source = repo_root / asset_rel
            dest = skill_dir / asset_rel
            if not dest.exists():
                errors.append(f"Missing '{asset_rel}' in skill '{skill_dir.name}'.")
            elif dest.read_bytes() != source.read_bytes():
                errors.append(f"Stale '{asset_rel}' in skill '{skill_dir.name}'.")

        if not (skill_dir / "agents" / "openai.yaml").exists():
            errors.append(
                f"Missing 'agents/openai.yaml' in skill '{skill_dir.name}'."
            )

    return errors


def generate_manifest(repo_root: Path) -> dict:
    """Generate manifest from skill directories.

    All skills — stable and experimental — share a single `skills` map. Each
    entry's `repo_dir` field ("skills" or "experimental") is the source of
    truth for whether the skill is experimental; consumers derive that state
    from `repo_dir`.
    """
    skills: dict = {}
    for skill_dir in iter_skill_dirs(repo_root):
        _add_skill(skills, _build_stable_entry(skill_dir))
    for skill_dir in iter_experimental_skill_dirs(repo_root):
        _add_skill(skills, _build_experimental_entry(skill_dir))

    return {
        "//": "GENERATED FILE: DO NOT EDIT. Run `python3 scripts/skills.py generate` to regenerate.",
        "version": "2",
        "skills": skills,
    }


def _add_skill(skills: dict, entry: tuple[str, dict]) -> None:
    name, skill = entry
    if name in skills:
        # Stable + experimental copies of the same logical skill can't coexist
        # in one map. The cli installs each entry under its plain skill name,
        # so a future collision must be resolved upstream (rename one of the
        # two, or merge them) before regenerating.
        raise ValueError(
            f"Duplicate skill name '{name}': present under both '{STABLE_REPO_DIR}/' "
            f"and '{EXPERIMENTAL_REPO_DIR}/'. Rename one to disambiguate."
        )
    skills[name] = skill


def _build_stable_entry(skill_dir: Path) -> tuple[str, dict]:
    files = sorted(str(f.relative_to(skill_dir)) for f in iter_skill_files(skill_dir))

    return skill_dir.name, {
        "version": extract_version_from_skill(skill_dir),
        "description": synthesize_short_description(skill_dir),
        "repo_dir": STABLE_REPO_DIR,
        "files": files,
    }


# Experimental skills have a looser contract than stable: no agents/openai.yaml
# required and no shared-asset sync. Description comes from SKILL.md frontmatter
# verbatim (including "Use when..." triggers).
def _build_experimental_entry(skill_dir: Path) -> tuple[str, dict]:
    files = sorted(str(f.relative_to(skill_dir)) for f in iter_skill_files(skill_dir))

    return skill_dir.name, {
        "version": extract_version_from_skill(skill_dir),
        "description": extract_description_from_skill(skill_dir),
        "repo_dir": EXPERIMENTAL_REPO_DIR,
        "files": files,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def serialize_manifest(manifest: dict) -> str:
    """Render manifest as its canonical on-disk form.

    `sort_keys=True` makes the skills map and each entry's keys alphabetical
    (the `files` arrays are already sorted at generation time). Validation
    requires the on-disk file to byte-equal this output — drift, hand-edits,
    or unsorted insertions all fail the check.
    """
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def validate_manifest(repo_root: Path) -> bool:
    """Validate that manifest.json is up to date AND in canonical sorted form."""
    manifest_path = repo_root / "manifest.json"

    if not manifest_path.exists():
        print("ERROR: manifest.json does not exist", file=sys.stderr)
        return False

    current_text = manifest_path.read_text()
    current_manifest = json.loads(current_text)
    expected_manifest = generate_manifest(repo_root)

    if current_manifest != expected_manifest:
        print("ERROR: manifest.json content is out of date", file=sys.stderr)
        print("\nExpected:", file=sys.stderr)
        print(serialize_manifest(expected_manifest), file=sys.stderr)
        print("\nActual:", file=sys.stderr)
        print(serialize_manifest(current_manifest), file=sys.stderr)
        return False

    if current_text != serialize_manifest(current_manifest):
        print(
            "ERROR: manifest.json is not in canonical sorted form. "
            "Keys must be alphabetical at every level.",
            file=sys.stderr,
        )
        return False

    return True


def validate_plugin_manifests(repo_root: Path) -> list[str]:
    """Validate .claude-plugin/plugin.json and .claude-plugin/marketplace.json
    stay in sync with the set of skills shipped in this repo.

    The two manifests power Claude Code marketplace discovery; if a new skill
    lands without a corresponding plugin keyword bump, the marketplace listing
    silently goes stale. This check forces SKILL_METADATA, plugin.json, and
    marketplace.json to stay aligned.

    Returns a list of error strings (empty means all good).
    """
    errors: list[str] = []

    plugin_path = repo_root / ".claude-plugin" / "plugin.json"
    marketplace_path = repo_root / ".claude-plugin" / "marketplace.json"

    if not plugin_path.exists():
        errors.append(f"Missing {plugin_path.relative_to(repo_root)}")
    if not marketplace_path.exists():
        errors.append(f"Missing {marketplace_path.relative_to(repo_root)}")
    if errors:
        return errors

    try:
        plugin = json.loads(plugin_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{plugin_path.relative_to(repo_root)} is not valid JSON: {exc}"]
    try:
        marketplace = json.loads(marketplace_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{marketplace_path.relative_to(repo_root)} is not valid JSON: {exc}"]

    keywords = {k.lower() for k in plugin.get("keywords", [])}

    for skill_dir in iter_skill_dirs(repo_root):
        meta = SKILL_METADATA.get(skill_dir.name)
        if meta is None:
            errors.append(
                f"Stable skill '{skill_dir.name}' has no SKILL_METADATA entry in "
                "scripts/skills.py. Add one with a 'plugin_keyword' so its Claude "
                "marketplace keyword in .claude-plugin/plugin.json stays in sync."
            )
            continue
        expected_keyword = meta.get("plugin_keyword")
        if not expected_keyword:
            errors.append(
                f"SKILL_METADATA['{skill_dir.name}'] is missing 'plugin_keyword'. "
                "Add one so .claude-plugin/plugin.json keywords coverage can be validated."
            )
            continue
        if expected_keyword.lower() not in keywords:
            errors.append(
                f"Skill '{skill_dir.name}' has no corresponding entry in "
                f".claude-plugin/plugin.json 'keywords' (looking for '{expected_keyword}'). "
                "Add it so the Claude marketplace listing stays in sync."
            )

    plugin_name = plugin.get("name")
    market_plugins = marketplace.get("plugins", [])
    market_entry = next((p for p in market_plugins if p.get("name") == plugin_name), None)
    if market_entry is None:
        errors.append(
            f".claude-plugin/marketplace.json has no entry for plugin '{plugin_name}'."
        )
    else:
        if market_entry.get("description") != plugin.get("description"):
            errors.append(
                ".claude-plugin/marketplace.json plugin description must match "
                ".claude-plugin/plugin.json description (they drift independently otherwise)."
            )

    return errors


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
        # validate_plugin_manifests reports the broken manifest itself; never
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

    claude_path = repo_root / ".claude-plugin" / "plugin.json"
    try:
        claude_version = json.loads(claude_path.read_text()).get("version")
    except Exception:
        claude_version = None
    if claude_version and plugin.get("version") != claude_version:
        errors.append(
            f'.codex-plugin/plugin.json version ({plugin.get("version")}) must match '
            f".claude-plugin/plugin.json ({claude_version}); scripts/bump_version.py "
            "keeps them in sync at release time."
        )

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
    codex_hooks = repo_root / "hooks" / "codex-hooks.json"
    if not codex_hooks.exists():
        errors.append("Missing hooks/codex-hooks.json.")
    else:
        try:
            cfg = json.loads(codex_hooks.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"hooks/codex-hooks.json is not valid JSON: {exc}")
            cfg = None
        if cfg is not None:
            blob = json.dumps(cfg)
            for script in sorted(set(re.findall(r"hooks/[\w.-]+\.py", blob))):
                if not (repo_root / script).exists():
                    errors.append(
                        f"hooks/codex-hooks.json references '{script}' which does not exist."
                    )

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

    claude_path = repo_root / ".claude-plugin" / "plugin.json"
    try:
        claude_version = json.loads(claude_path.read_text()).get("version")
    except Exception:
        claude_version = None
    if claude_version and plugin.get("version") != claude_version:
        errors.append(
            f'.github/plugin/plugin.json version ({plugin.get("version")}) must match '
            f".claude-plugin/plugin.json ({claude_version}); scripts/bump_version.py "
            "keeps them in sync at release time."
        )

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
    copilot_hooks = repo_root / "hooks" / "copilot-hooks.json"
    if not copilot_hooks.exists():
        errors.append("Missing hooks/copilot-hooks.json.")
    else:
        try:
            cfg = json.loads(copilot_hooks.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"hooks/copilot-hooks.json is not valid JSON: {exc}")
            cfg = None
        if cfg is not None:
            if cfg.get("version") != 1:
                errors.append('hooks/copilot-hooks.json must declare "version": 1.')
            blob = json.dumps(cfg)
            for script in sorted(set(re.findall(r"hooks/[\w.-]+\.py", blob))):
                if not (repo_root / script).exists():
                    errors.append(
                        f"hooks/copilot-hooks.json references '{script}' which does not exist."
                    )

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
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage skills: sync shared assets, generate manifest, validate."
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="generate",
        choices=["sync", "generate", "validate"],
        help=(
            "sync: ensure every skill has assets + agents/openai.yaml. "
            "generate: sync + (re)build manifest.json (default). "
            "validate: check assets, metadata, and manifest are up to date."
        ),
    )

    args = parser.parse_args()
    repo_root = Path(__file__).parent.parent

    match args.mode:
        case "sync":
            written = ensure_codex_metadata(repo_root)
            print(f"Wrote {written} Codex-metadata file(s)")

        case "generate":
            written = ensure_codex_metadata(repo_root)
            print(f"Wrote {written} Codex-metadata file(s)")

            manifest = generate_manifest(repo_root)
            manifest_path = repo_root / "manifest.json"
            manifest_path.write_text(serialize_manifest(manifest))
            print(f"Generated {manifest_path}")
            print(
                f"Found {len(manifest['skills'])} skill(s): "
                f"{', '.join(manifest['skills'].keys())}"
            )

        case "validate":
            ok = True

            metadata_errors = check_codex_metadata(repo_root)
            if metadata_errors:
                print(
                    "ERROR: Skill assets / Codex metadata are out of sync:",
                    file=sys.stderr,
                )
                for err in metadata_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            if not validate_manifest(repo_root):
                ok = False

            plugin_errors = validate_plugin_manifests(repo_root)
            if plugin_errors:
                print(
                    "ERROR: .claude-plugin manifests are out of sync with skills:",
                    file=sys.stderr,
                )
                for err in plugin_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            component_errors = check_plugin_components(repo_root)
            if component_errors:
                print(
                    "ERROR: plugin components (hooks/ + commands/) are misconfigured:",
                    file=sys.stderr,
                )
                for err in component_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            codex_errors = check_codex_plugin(repo_root)
            if codex_errors:
                print(
                    "ERROR: Codex plugin manifests / hooks are misconfigured:",
                    file=sys.stderr,
                )
                for err in codex_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            copilot_errors = check_copilot_plugin(repo_root)
            if copilot_errors:
                print(
                    "ERROR: Copilot plugin manifests / hooks are misconfigured:",
                    file=sys.stderr,
                )
                for err in copilot_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            if not ok:
                print(
                    "\nRun `python3 scripts/skills.py generate` to fix the "
                    "manifest, and update .claude-plugin/plugin.json + "
                    "marketplace.json by hand for any plugin-keyword/description "
                    "mismatches.",
                    file=sys.stderr,
                )
                sys.exit(1)

            print("Everything is up to date.")


if __name__ == "__main__":
    main()
