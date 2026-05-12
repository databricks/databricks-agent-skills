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

SKILL_METADATA = {
    "databricks-core": {
        "description": "Core Databricks skill for CLI, auth, and data exploration",
    },
    "databricks-apps": {
        "description": "Databricks Apps development and deployment (evaluates analytics vs synced tables data access)",
    },
    "databricks-jobs": {
        "description": "Develop and deploy Lakeflow Jobs on Databricks via DABs, Python SDK, or the CLI — covers all task types, triggers, notifications, and worked examples",
    },
    "databricks-lakebase": {
        "description": "Databricks Lakebase Postgres: projects, scaling, connectivity, synced tables, and Data API",
    },
    "databricks-dabs": {
        "description": "Declarative Automation Bundles (DABs) for deploying and managing Databricks resources",
    },
    "databricks-model-serving": {
        "description": "Databricks Model Serving endpoint management",
    },
    "databricks-pipelines": {
        "description": "Databricks Spark Declarative Pipelines (SDP) for ETL and streaming",
    },
    "databricks-serverless-migration": {
        "description": "Migrate Databricks workloads from classic compute to serverless compute, including compatibility checks and concrete fixes",
    },
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

def sync_assets(repo_root: Path) -> int:
    """Copy shared assets from repo root into each skill directory.

    Only writes when content differs. Uses shutil.copy2 to preserve mtime
    from the source.

    Returns count of files written.
    """
    for asset_rel in SHARED_ASSETS:
        source = repo_root / asset_rel
        if not source.exists():
            raise ValueError(f"Missing shared asset '{asset_rel}' at repo root.")

    synced = 0
    for skill_dir in iter_skill_dirs(repo_root):
        for asset_rel in SHARED_ASSETS:
            source = repo_root / asset_rel
            dest = skill_dir / asset_rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists() and dest.read_bytes() == source.read_bytes():
                continue

            shutil.copy2(source, dest)
            synced += 1

    return synced


def check_assets_synced(repo_root: Path) -> list[str]:
    """Validate that all shared assets are present and up-to-date.

    Returns a list of error messages (empty means all good).
    """
    errors: list[str] = []
    for asset_rel in SHARED_ASSETS:
        source = repo_root / asset_rel
        if not source.exists():
            errors.append(f"Missing shared asset '{asset_rel}' at repo root.")
            continue

        source_bytes = source.read_bytes()
        for skill_dir in iter_skill_dirs(repo_root):
            dest = skill_dir / asset_rel
            if not dest.exists():
                errors.append(f"Missing '{asset_rel}' in skill '{skill_dir.name}'.")
            elif dest.read_bytes() != source_bytes:
                errors.append(f"Stale '{asset_rel}' in skill '{skill_dir.name}'.")

    return errors


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


def ensure_experimental_codex_metadata(repo_root: Path) -> int:
    """Synthesize agents/openai.yaml and copy shared assets for experimental skills.

    Only writes when files are missing — upstream ai-dev-kit can override by
    shipping its own agents/openai.yaml or assets/ in the skill. Returns the
    number of files written.
    """
    written = 0
    for skill_dir in iter_experimental_skill_dirs(repo_root):
        for asset_rel in SHARED_ASSETS:
            source = repo_root / asset_rel
            dest = skill_dir / asset_rel
            if dest.exists():
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


def generate_manifest(repo_root: Path) -> dict:
    """Generate manifest from skill directories.

    All skills — stable and experimental — share a single `skills` map. Each
    entry's `repo_dir` field ("skills" or "experimental") is the source of
    truth for whether the skill is experimental; consumers derive that state
    from `repo_dir`.
    """
    manifest_path = repo_root / "manifest.json"
    existing_skills = {}
    if manifest_path.exists():
        existing_skills = json.loads(manifest_path.read_text()).get("skills", {})

    skills: dict = {}
    for skill_dir in iter_skill_dirs(repo_root):
        _add_skill(skills, _build_stable_entry(skill_dir, existing_skills))
    for skill_dir in iter_experimental_skill_dirs(repo_root):
        _add_skill(skills, _build_experimental_entry(skill_dir, existing_skills))

    return {
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


def _build_stable_entry(skill_dir: Path, existing_skills: dict) -> tuple[str, dict]:
    if skill_dir.name not in SKILL_METADATA:
        raise ValueError(
            f"Missing SKILL_METADATA entry for skill '{skill_dir.name}'. "
            "Add it to SKILL_METADATA dict."
        )

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        raise ValueError(
            f"Missing agents/openai.yaml in skill '{skill_dir.name}'. "
            "Each skill must include Codex marketplace metadata."
        )

    metadata = SKILL_METADATA[skill_dir.name]
    files = sorted(str(f.relative_to(skill_dir)) for f in iter_skill_files(skill_dir))

    skill_entry = {
        "version": extract_version_from_skill(skill_dir),
        "description": metadata.get("description", ""),
        "repo_dir": STABLE_REPO_DIR,
        "files": files,
    }

    if metadata.get("min_cli_version"):
        skill_entry["min_cli_version"] = metadata["min_cli_version"]

    existing = existing_skills.get(skill_dir.name, {})
    if "base_revision" in existing:
        skill_entry["base_revision"] = existing["base_revision"]

    return skill_dir.name, skill_entry


# Experimental skills have a looser contract than stable: no agents/openai.yaml
# required, no shared-asset sync, no SKILL_METADATA entry required. Description
# is scraped from SKILL.md frontmatter on a best-effort basis.
def _build_experimental_entry(skill_dir: Path, existing_skills: dict) -> tuple[str, dict]:
    files = sorted(str(f.relative_to(skill_dir)) for f in iter_skill_files(skill_dir))

    skill_entry = {
        "version": extract_version_from_skill(skill_dir),
        "description": extract_description_from_skill(skill_dir),
        "repo_dir": EXPERIMENTAL_REPO_DIR,
        "files": files,
    }

    existing = existing_skills.get(skill_dir.name, {})
    if "base_revision" in existing:
        skill_entry["base_revision"] = existing["base_revision"]

    return skill_dir.name, skill_entry


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def normalize_manifest(manifest: dict) -> dict:
    """Normalize manifest for comparison by excluding volatile fields."""
    normalized = manifest.copy()
    normalized["skills"] = _normalize_skill_map(manifest.get("skills", {}))
    return normalized


def _normalize_skill_map(skill_map: dict) -> dict:
    out = {}
    for name, skill in skill_map.items():
        skill_copy = skill.copy()
        skill_copy.pop("base_revision", None)
        out[name] = skill_copy
    return out


def validate_manifest(repo_root: Path) -> bool:
    """Validate that manifest.json is up to date. Returns True if valid."""
    manifest_path = repo_root / "manifest.json"

    if not manifest_path.exists():
        print("ERROR: manifest.json does not exist", file=sys.stderr)
        return False

    current_manifest = json.loads(manifest_path.read_text())
    expected_manifest = generate_manifest(repo_root)

    current_normalized = normalize_manifest(current_manifest)
    expected_normalized = normalize_manifest(expected_manifest)

    if current_normalized != expected_normalized:
        print("ERROR: manifest.json is out of date", file=sys.stderr)
        print("\nExpected:", file=sys.stderr)
        print(json.dumps(expected_normalized, indent=2), file=sys.stderr)
        print("\nActual:", file=sys.stderr)
        print(json.dumps(current_normalized, indent=2), file=sys.stderr)
        return False

    return True


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
            "sync: copy shared assets into each skill directory. "
            "generate: sync + create manifest.json (default). "
            "validate: check assets and manifest are up to date."
        ),
    )

    args = parser.parse_args()
    repo_root = Path(__file__).parent.parent

    match args.mode:
        case "sync":
            synced = sync_assets(repo_root)
            print(f"Synced {synced} asset(s)")
            generated = ensure_experimental_codex_metadata(repo_root)
            print(f"Generated {generated} experimental Codex metadata file(s)")

        case "generate":
            synced = sync_assets(repo_root)
            print(f"Synced {synced} asset(s)")
            generated = ensure_experimental_codex_metadata(repo_root)
            print(f"Generated {generated} experimental Codex metadata file(s)")

            manifest = generate_manifest(repo_root)
            manifest_path = repo_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            print(f"Generated {manifest_path}")
            print(
                f"Found {len(manifest['skills'])} skill(s): "
                f"{', '.join(manifest['skills'].keys())}"
            )

        case "validate":
            ok = True

            asset_errors = check_assets_synced(repo_root)
            if asset_errors:
                print("ERROR: Shared assets are out of sync:", file=sys.stderr)
                for err in asset_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            if not validate_manifest(repo_root):
                ok = False

            if not ok:
                print(
                    "\nRun `python3 scripts/skills.py generate` to fix.",
                    file=sys.stderr,
                )
                sys.exit(1)

            print("Everything is up to date.")


if __name__ == "__main__":
    main()
