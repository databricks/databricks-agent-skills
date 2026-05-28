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

    plugin = json.loads(plugin_path.read_text())
    marketplace = json.loads(marketplace_path.read_text())

    keywords = {k.lower() for k in plugin.get("keywords", [])}

    for skill_dir in iter_skill_dirs(repo_root):
        meta = SKILL_METADATA.get(skill_dir.name)
        if meta is None:
            continue  # generate_manifest will flag the missing metadata
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
