"""Skill discovery, SKILL.md frontmatter extraction, and Codex metadata sync."""

import re
import shutil
from pathlib import Path

from skillsgen.common import _read_frontmatter


SHARED_ASSETS = [
    "assets/databricks.svg",
    "assets/databricks.png",
]

# Stable directory: "skills/<name>/". Experimental: "experimental/<name>/".
# The wire format carries each entry's source directory in `repo_dir`; consumers
# derive experimental state from that. No parallel `experimental_skills` map.
# The CLI's files-channel fetches stable skills from the root skills/ (the
# editable source on the published repo), so repo_dir stays "skills" even though
# the plugin bundles carry their own per-provider copies under plugins/databricks/.
STABLE_REPO_DIR = "skills"
EXPERIMENTAL_REPO_DIR = "experimental"

UNPUBLISHED_FILENAMES = frozenset(
    {
        "BUILD",
        "BUILD.bazel",
        "METADATA",
        "OWNERS",
    }
)


def is_publishable_path(relative_parts: tuple[str, ...]) -> bool:
    """Return whether a source path may appear in a published artifact."""
    if any(part.startswith(".") for part in relative_parts):
        return False
    if "__pycache__" in relative_parts:
        return False
    if any(part.endswith(".pyc") for part in relative_parts):
        return False
    return not any(part in UNPUBLISHED_FILENAMES for part in relative_parts)


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


# CLI command groups a skill covers, read from `metadata.cli_command_groups`. The value
# is a quoted string of comma-separated groups (`cli_command_groups: "bundle, air"`),
# because the Agent Skills spec gives `metadata` string values only.
CLI_COMMAND_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_CLI_COMMAND_GROUPS_DIRECT_RE = re.compile(
    r"(?:\"cli_command_groups\"|'cli_command_groups'|cli_command_groups)[ \t]*:(.*)"
)
# A line that starts with the key (quoted or not), so prose that merely mentions
# `cli_command_groups:` in the middle of a line is not a key.
_CLI_KEY_START_RE = re.compile(r"[\"']?cli_command_groups[\"']?[ \t]*:")
# The key inside a flow mapping, such as `metadata: {cli_command_groups: bundle}`.
_CLI_FLOW_KEY_RE = re.compile(r"[{,][ \t]*[\"']?cli_command_groups[\"']?[ \t]*:")
# The top-level `metadata:` key, quoted or not, that the field must sit under.
_CLI_METADATA_KEY_RE = re.compile(r"[\"']?metadata[\"']?[ \t]*:")
# A `key: |` or `key: >-` line; the indented lines under it are text, not keys.
_BLOCK_SCALAR_HEADER_RE = re.compile(r"[^\s#][^:]*:[ \t]*[|>][0-9+-]*(?:[ \t]+#.*)?")
# A quoted value, with an optional YAML comment after the closing quote.
_QUOTED_VALUE_RE = re.compile(r"([\"'])(.*?)\1(?:[ \t]+#.*)?")


def cli_command_groups_error(names: object) -> str | None:
    """Return why `names` is not a list of unique lowercase command group names.

    Returns None when it is valid. The frontmatter reader and the committed-manifest
    check both call this, so they share one rule.
    """
    if not isinstance(names, list):
        return "must be a list of command group names."
    for name in names:
        if not isinstance(name, str) or not CLI_COMMAND_NAME_RE.fullmatch(name):
            return (
                f"entry {name!r} is not a lowercase command group name (letters, "
                "digits and hyphens, starting with a letter)."
            )
    if len(set(names)) != len(names):
        return f"lists a duplicate entry: {names!r}."
    return None


def _parse_cli_command_groups_value(raw: str) -> list[str]:
    """Parse the quoted string value of `cli_command_groups` into command group names."""
    quoted = _QUOTED_VALUE_RE.fullmatch(raw)
    if quoted is None:
        raise ValueError(
            "metadata.cli_command_groups must be a quoted string of command group names, "
            f'such as "bundle" or "bundle, air"; got {raw!r}.'
        )
    inner = quoted.group(2)
    names = [part.strip() for part in inner.split(",")] if inner.strip() else []
    error = cli_command_groups_error(names)
    if error is not None:
        raise ValueError(f"metadata.cli_command_groups {error}")
    return names


def read_cli_command_groups(skill_path: Path) -> list[str]:
    """Return the CLI command groups in `metadata.cli_command_groups`, or [] if absent.

    Raises ValueError when the field is present but is not a quoted string of
    unique lowercase command group names, or sits anywhere other than a direct
    child of a plain `metadata:` key. Fails closed: a `cli_command_groups` key the
    reader cannot place is an error, never a silently missing mapping.
    """
    frontmatter = _read_frontmatter(skill_path / "SKILL.md")
    if frontmatter is None:
        return []
    raw = None
    in_metadata = False
    child_indent = None
    block_indent = None
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if block_indent is not None:
            if indent > block_indent:
                continue  # text of a block scalar, such as a description
            block_indent = None
        if indent == 0:
            in_metadata = _CLI_METADATA_KEY_RE.match(stripped) is not None
            child_indent = None
        elif in_metadata and child_indent is None:
            child_indent = indent
        if _BLOCK_SCALAR_HEADER_RE.fullmatch(stripped):
            block_indent = indent
        direct = None
        if in_metadata and indent == child_indent:
            direct = _CLI_COMMAND_GROUPS_DIRECT_RE.match(stripped)
        misplaced_key = _CLI_KEY_START_RE.match(stripped) and (indent == 0 or in_metadata)
        flow_key = in_metadata and _CLI_FLOW_KEY_RE.search(stripped)
        if direct:
            if raw is not None:
                raise ValueError("metadata.cli_command_groups is set more than once.")
            raw = direct.group(1).strip()
        elif misplaced_key or flow_key:
            raise ValueError(
                "metadata.cli_command_groups must be a direct child of a plain `metadata:` "
                "key, on its own line."
            )
    if raw is None:
        return []
    return _parse_cli_command_groups_value(raw)


def iter_skill_files(skill_path: Path):
    """Yield files in a skill directory that may be published.

    This applies the same governance and generated-file exclusions as bundle
    generation so the manifest and provider artifacts cannot diverge.
    """
    for file_path in skill_path.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = file_path.relative_to(skill_path).parts
        if not is_publishable_path(rel_parts):
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

BLOCK_SCALAR_INDICATORS = frozenset({"|", "|-", "|+", ">", ">-", ">+"})


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
        if value in BLOCK_SCALAR_INDICATORS:
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
    "databricks-lakeflow-connect-saas": "Databricks Lakeflow Connect SaaS",
    "databricks-mlflow-evaluation": "Databricks MLflow Evaluation",
    "databricks-setup-local": "Databricks Local Environment Setup",
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
