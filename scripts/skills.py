#!/usr/bin/env python3
"""Manage skills: sync shared assets, generate manifest, validate."""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


SHARED_ASSETS = [
    "assets/databricks.svg",
    "assets/databricks.png",
]

SKILL_METADATA = {
    "databricks-core": {
        "description": "Core Databricks skill for CLI, auth, and data exploration",
        "experimental": False,
    },
    "databricks-apps": {
        "description": "Databricks Apps development and deployment",
        "experimental": False,
    },
    "databricks-jobs": {
        "description": "Databricks Jobs orchestration and scheduling",
        "experimental": False,
    },
    "databricks-lakebase": {
        "description": "Databricks Lakebase database development",
        "experimental": False,
    },
    "databricks-dabs": {
        "description": "Declarative Automation Bundles (DABs) for deploying and managing Databricks resources",
        "experimental": False,
    },
    "databricks-model-serving": {
        "description": "Databricks Model Serving endpoint management",
        "experimental": False,
    },
    "databricks-pipelines": {
        "description": "Databricks Pipelines (DLT) for ETL and streaming",
        "experimental": False,
    },
    "databricks-serverless-migration": {
        "description": "Migrate Databricks workloads from classic compute to serverless compute, including compatibility checks and concrete fixes",
        "experimental": False,
    },
}


def iter_skill_dirs(repo_root: Path):
    """Yield skill directories that contain SKILL.md."""
    skills_dir = repo_root / "skills"
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith(".") or item.name == "scripts":
            continue
        if not (item / "SKILL.md").exists():
            continue
        yield item


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

    return "0.0.0"


def iter_skill_files(skill_path: Path):
    """Yield tracked files in a skill directory, skipping VCS-ignored noise.

    Filters out dot-prefixed paths (.DS_Store, .git, etc.), __pycache__
    directories, and *.pyc files so manifest output and updated_at timestamps
    stay reproducible across machines.
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


def get_skill_updated_at(skill_path: Path) -> str:
    """Get the most recent modification time of any file in the skill directory."""
    latest_mtime = 0.0
    for file_path in iter_skill_files(skill_path):
        mtime = file_path.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime

    if latest_mtime == 0.0:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return datetime.fromtimestamp(latest_mtime, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync_assets(repo_root: Path) -> int:
    """Copy shared assets from repo root into each skill directory.

    Only writes when content differs. Uses shutil.copy2 to preserve mtime
    from the source so that skill updated_at timestamps stay stable.

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

def generate_manifest(repo_root: Path) -> dict:
    """Generate manifest from skill directories."""
    manifest_path = repo_root / "manifest.json"
    existing_skills = {}
    if manifest_path.exists():
        existing_skills = json.loads(manifest_path.read_text()).get("skills", {})

    skills = {}
    for skill_dir in iter_skill_dirs(repo_root):
        files = sorted(
            str(f.relative_to(skill_dir))
            for f in iter_skill_files(skill_dir)
        )

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
        skill_entry = {
            "version": extract_version_from_skill(skill_dir),
            "description": metadata.get("description", ""),
            "experimental": metadata.get("experimental", False),
            "updated_at": get_skill_updated_at(skill_dir),
            "files": files,
        }

        if metadata.get("min_cli_version"):
            skill_entry["min_cli_version"] = metadata["min_cli_version"]

        existing = existing_skills.get(skill_dir.name, {})
        if "base_revision" in existing:
            skill_entry["base_revision"] = existing["base_revision"]

        skills[skill_dir.name] = skill_entry

    return {
        "version": "2",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skills": skills,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def normalize_manifest(manifest: dict) -> dict:
    """Normalize manifest for comparison by excluding volatile fields."""
    normalized = manifest.copy()
    normalized.pop("updated_at", None)

    skills = {}
    for name, skill in manifest.get("skills", {}).items():
        skill_copy = skill.copy()
        skill_copy.pop("updated_at", None)
        skill_copy.pop("base_revision", None)
        skills[name] = skill_copy

    normalized["skills"] = skills
    return normalized


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

        case "generate":
            synced = sync_assets(repo_root)
            print(f"Synced {synced} asset(s)")

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
