"""manifest.json generation and validation."""

import json
import sys
from pathlib import Path

from skillsgen.common import _norm_rel_path
from skillsgen.discovery import (
    EXPERIMENTAL_REPO_DIR,
    STABLE_REPO_DIR,
    extract_description_from_skill,
    extract_version_from_skill,
    iter_experimental_skill_dirs,
    iter_skill_dirs,
    iter_skill_files,
    synthesize_short_description,
)


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


def _is_safe_manifest_path(path: str) -> bool:
    path = _norm_rel_path(path)
    rel = Path(path)
    return bool(path) and not rel.is_absolute() and ".." not in rel.parts


def check_manifest_file_references(repo_root: Path) -> list[str]:
    """Validate that a committed manifest cannot point the CLI at 404s.

    The publish repo can carry a generated manifest between releases while
    source skills change on main. The CLI's files-channel installer reads that
    committed manifest directly, so validate every advertised skill directory
    and file before CI's dry-run regeneration masks stale entries.
    """
    manifest_path = repo_root / "manifest.json"
    if not manifest_path.exists():
        return []

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"manifest.json is not valid JSON: {exc}"]

    skills = manifest.get("skills")
    if not isinstance(skills, dict):
        return ['manifest.json "skills" must be an object.']

    errors: list[str] = []
    for name, entry in sorted(skills.items()):
        if not isinstance(entry, dict):
            errors.append(f'manifest.json skills["{name}"] must be an object.')
            continue

        repo_dir = entry.get("repo_dir")
        if not isinstance(repo_dir, str):
            errors.append(
                f'manifest.json skills["{name}"].repo_dir must be a string.'
            )
            continue

        repo_dir = _norm_rel_path(repo_dir)
        if repo_dir not in {STABLE_REPO_DIR, EXPERIMENTAL_REPO_DIR}:
            errors.append(
                f'manifest.json skills["{name}"].repo_dir is {repo_dir!r}; '
                f"expected {STABLE_REPO_DIR!r} or {EXPERIMENTAL_REPO_DIR!r}."
            )
            continue

        if not _is_safe_manifest_path(name) or Path(name).name != name:
            errors.append(
                f"manifest.json skill name {name!r} is not a safe directory name."
            )
            continue

        skill_root = repo_root / repo_dir / name
        if not skill_root.is_dir():
            errors.append(
                f"manifest.json lists skill '{name}' at {repo_dir}/{name}, "
                "but that directory does not exist. Regenerate manifest.json "
                "or restore the skill."
            )
            continue

        files = entry.get("files")
        if not isinstance(files, list):
            errors.append(f'manifest.json skills["{name}"].files must be an array.')
            continue

        for file_rel in files:
            if not isinstance(file_rel, str) or not _is_safe_manifest_path(file_rel):
                errors.append(
                    f"manifest.json lists unsafe file path {file_rel!r} "
                    f"for skill '{name}'."
                )
                continue

            file_rel = _norm_rel_path(file_rel)
            if not (skill_root / file_rel).is_file():
                errors.append(
                    f"manifest.json lists file '{file_rel}' for skill '{name}', "
                    f"but {repo_dir}/{name}/{file_rel} does not exist. "
                    "Regenerate manifest.json or restore the file."
                )

    return errors


def validate_manifest(repo_root: Path) -> bool:
    """Validate that manifest.json is up to date AND in canonical sorted form."""
    manifest_path = repo_root / "manifest.json"

    if not manifest_path.exists():
        print("ERROR: manifest.json does not exist", file=sys.stderr)
        return False

    reference_errors = check_manifest_file_references(repo_root)
    if reference_errors:
        print(
            "ERROR: manifest.json points at missing or invalid skill files:",
            file=sys.stderr,
        )
        for err in reference_errors:
            print(f"  - {err}", file=sys.stderr)
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
