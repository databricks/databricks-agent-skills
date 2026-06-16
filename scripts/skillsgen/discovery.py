"""Skill discovery, SKILL.md frontmatter extraction, and Codex metadata sync."""

import re
import shutil
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
# trigger/instruction tail. The marketplace short_description should only
# contain the lead-in. ". Load this" trims the parent skill's "Load this first
# ..., then load the matching product skill" agent-instruction tail
# (databricks-core), which otherwise overran the 200-char cap and truncated
# mid-word to "...Load this firs...". First marker found (in list order) wins,
# so this only affects descriptions that don't already match an earlier marker.
_SHORT_DESC_MARKERS = (". Use when", ". Use this", ". Triggers", ". ALWAYS", ". Load this")


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
