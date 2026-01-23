#!/usr/bin/env python3
"""Generate or validate manifest.json from skill directories."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def extract_version_from_skill(skill_path: Path) -> str:
    """Extract version from SKILL.md frontmatter metadata."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"SKILL.md not found in {skill_path}")

    content = skill_md.read_text()

    # parse YAML frontmatter
    if not content.startswith("---"):
        raise ValueError(f"SKILL.md in {skill_path} missing frontmatter")

    end_idx = content.find("---", 3)
    if end_idx == -1:
        raise ValueError(f"SKILL.md in {skill_path} has unclosed frontmatter")

    frontmatter = content[3:end_idx]

    # extract version from metadata block
    version_match = re.search(r'version:\s*["\']?([^"\'\n]+)["\']?', frontmatter)
    if version_match:
        return version_match.group(1).strip()

    return "0.0.0"


def get_skill_updated_at(skill_path: Path) -> str:
    """Get the most recent modification time of any file in the skill directory."""
    latest_mtime = 0.0
    for file_path in skill_path.rglob("*"):
        if file_path.is_file():
            mtime = file_path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime

    if latest_mtime == 0.0:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return datetime.fromtimestamp(latest_mtime, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def generate_manifest(repo_root: Path) -> dict:
    """Generate manifest from skill directories."""
    skills = {}

    skills_dir = repo_root / "skills"

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith(".") or item.name == "scripts":
            continue

        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue

        skills[item.name] = {
            "version": extract_version_from_skill(item),
            "updated_at": get_skill_updated_at(item),
        }

    return {
        "version": "1",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skills": skills,
    }


def normalize_manifest(manifest: dict) -> dict:
    """Normalize manifest for comparison by excluding updated_at timestamps."""
    normalized = manifest.copy()
    normalized.pop("updated_at", None)

    skills = {}
    for name, skill in manifest.get("skills", {}).items():
        skill_copy = skill.copy()
        skill_copy.pop("updated_at", None)
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

    # compare without timestamps
    current_normalized = normalize_manifest(current_manifest)
    expected_normalized = normalize_manifest(expected_manifest)

    if current_normalized != expected_normalized:
        print("ERROR: manifest.json is out of date", file=sys.stderr)
        print("\nExpected:", file=sys.stderr)
        print(json.dumps(expected_normalized, indent=2), file=sys.stderr)
        print("\nActual:", file=sys.stderr)
        print(json.dumps(current_normalized, indent=2), file=sys.stderr)
        return False

    print("manifest.json is up to date")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or validate manifest.json")
    parser.add_argument(
        "mode",
        choices=["generate", "validate"],
        help="Mode: generate (creates manifest.json) or validate (checks if up to date)",
    )

    args = parser.parse_args()
    repo_root = Path(__file__).parent.parent

    match args.mode:
        case "generate":
            manifest = generate_manifest(repo_root)
            manifest_path = repo_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            print(f"Generated {manifest_path}")
            print(f"Found {len(manifest['skills'])} skill(s): {', '.join(manifest['skills'].keys())}")

        case "validate":
            is_valid = validate_manifest(repo_root)
            sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
