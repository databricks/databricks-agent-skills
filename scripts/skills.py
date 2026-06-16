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

# Plugin-level metadata (version, identity, keywords, description, per-target
# shape) is the single source of truth in plugin.meta.json at the repo root.
# load_meta reads it; the build_* renderers below generate every target's
# plugin.json + marketplace.json from it. The skill -> plugin-keyword map that
# used to live here (SKILL_METADATA) now lives in plugin.meta.json "skills".
META_FILE = "plugin.meta.json"


def load_meta(repo_root: Path) -> dict:
    """Load plugin.meta.json (the cross-target plugin source of truth)."""
    return json.loads((repo_root / META_FILE).read_text())


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


# ---------------------------------------------------------------------------
# Plugin manifests (generated from plugin.meta.json for every target)
# ---------------------------------------------------------------------------
#
# One logical plugin ships to four targets (Claude Code, Codex, Copilot,
# Cursor) plus a marketplace catalog for three of them. Every target used to
# keep a hand-edited copy of the same plugin-level metadata (version,
# description, keywords, author, ...) and they drifted: version duplicated 4x,
# Codex missing the app-design keyword, Cursor's description stale. plugin.meta.json
# is now the single source; the build_* renderers below assemble each target's
# file from it in that target's exact key order, and check_generated_plugins
# fails CI on any drift. Stdlib-only, like the rest of this file.
#
# These JSON files are consumed by strict plugin loaders / a JSON-schema
# validator (the Claude marketplace `$schema`), so they carry NO "//" comment
# key (unlike manifest.json, whose consumer tolerates it). Their generated
# status is documented in CONTRIBUTING.md and enforced by the drift check.

_CLAUDE_MARKETPLACE_SCHEMA = (
    "https://json.schemastore.org/claude-code-plugin-marketplace.json"
)


def _serialize_plugin_json(obj: dict) -> str:
    """Canonical on-disk form for a generated plugin JSON file.

    2-space indent, insertion-ordered keys (NOT sorted — each target's key
    order is reproduced by the build_* function), trailing newline.
    """
    return json.dumps(obj, indent=2) + "\n"


def build_keywords(meta: dict) -> list[str]:
    """Compose the plugin keyword list from meta.

    keywords = keywords_lead + [each skill's keyword, in meta order] +
    keywords_tail. The lead/tail hold cross-cutting terms owned by no single
    skill ("databricks", "data-engineering"); the middle is one keyword per
    shipped skill, ordered by the insertion order of meta["skills"].
    """
    skill_keywords = [entry["keyword"] for entry in meta["skills"].values()]
    return [
        *meta.get("keywords_lead", []),
        *skill_keywords,
        *meta.get("keywords_tail", []),
    ]


def build_claude_plugin(meta: dict) -> dict:
    return {
        "name": meta["name"],
        "description": meta["description"],
        "version": meta["version"],
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "keywords": build_keywords(meta),
        "skills": "./skills/",
        "commands": meta["targets"]["claude"]["commands"],
    }


def build_codex_plugin(meta: dict) -> dict:
    target = meta["targets"]["codex"]
    return {
        "name": meta["name"],
        "description": meta["description"],
        "version": meta["version"],
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "keywords": build_keywords(meta),
        "skills": "./skills/",
        "hooks": target["hooks"],
        "interface": target["interface"],
    }


def build_copilot_plugin(meta: dict) -> dict:
    target = meta["targets"]["copilot"]
    return {
        "name": meta["name"],
        "displayName": target["displayName"],
        "description": meta["description"],
        "version": meta["version"],
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
        "skills": "./skills/",
        "hooks": target["hooks"],
    }


def build_cursor_plugin(meta: dict) -> dict:
    target = meta["targets"]["cursor"]
    # Cursor omits homepage/repository/license and ships the author name only.
    return {
        "name": meta["name"],
        "displayName": target["displayName"],
        "description": meta["description"],
        "version": meta["version"],
        "author": {"name": meta["author"]["name"]},
        "skills": "./skills/",
        "commands": target["commands"],
        "rules": target["rules"],
        "hooks": target["hooks"],
    }


def build_claude_marketplace(meta: dict) -> dict:
    market = meta["marketplace"]
    return {
        "$schema": _CLAUDE_MARKETPLACE_SCHEMA,
        "name": market["name"],
        "description": market["description"],
        "owner": market["owner"],
        "plugins": [
            {
                "name": meta["name"],
                "source": "./",
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


def build_copilot_marketplace(meta: dict) -> dict:
    market = meta["marketplace"]
    return {
        "name": market["name"],
        "description": market["description"],
        "owner": market["owner"],
        "plugins": [
            {
                "name": meta["name"],
                "source": "./",
                "category": meta["category"],
                "description": meta["description"],
            }
        ],
    }


def build_codex_marketplace(meta: dict) -> dict:
    market = meta["marketplace"]
    return {
        "name": market["name"],
        "interface": {"displayName": market["displayName"]},
        "plugins": [
            {
                "name": meta["name"],
                "description": meta["description"],
                "category": meta["category"],
                "source": {"source": "local", "path": "./"},
            }
        ],
    }


# Marker dropped in every generated-manifest directory. The JSON files
# themselves cannot carry a "do not edit" comment (their loaders / the Claude
# marketplace $schema reject unknown keys), so this sibling README is the
# in-folder signal that the directory is generated. It is part of the generated
# set, so the drift check keeps it present and current.
_GENERATED_README = """\
<!-- GENERATED FILE: do not edit by hand. -->

# Generated plugin manifests

The plugin manifest files in this directory (`plugin.json` and/or
`marketplace.json`) are generated from the repo-root `plugin.meta.json` by
`scripts/skills.py`. To change them, edit `plugin.meta.json` and run
`python3 scripts/skills.py generate`. CI re-renders these files and fails on any
drift, so hand-edits are reverted. See `CONTRIBUTING.md` ("Plugin metadata").
"""

# Directories whose plugin/marketplace JSON is generated; each gets the marker.
_GENERATED_MANIFEST_DIRS = (
    ".claude-plugin",
    ".codex-plugin",
    ".github/plugin",
    ".cursor-plugin",
    ".agents/plugins",
)


def generated_plugin_files(meta: dict) -> dict:
    """Map every generated plugin file (repo-relative path -> canonical text)."""
    files = {
        ".claude-plugin/plugin.json": _serialize_plugin_json(build_claude_plugin(meta)),
        ".codex-plugin/plugin.json": _serialize_plugin_json(build_codex_plugin(meta)),
        ".github/plugin/plugin.json": _serialize_plugin_json(build_copilot_plugin(meta)),
        ".cursor-plugin/plugin.json": _serialize_plugin_json(build_cursor_plugin(meta)),
        ".claude-plugin/marketplace.json": _serialize_plugin_json(
            build_claude_marketplace(meta)
        ),
        ".github/plugin/marketplace.json": _serialize_plugin_json(
            build_copilot_marketplace(meta)
        ),
        ".agents/plugins/marketplace.json": _serialize_plugin_json(
            build_codex_marketplace(meta)
        ),
    }
    for directory in _GENERATED_MANIFEST_DIRS:
        files[f"{directory}/README.md"] = _GENERATED_README
    return files


def generate_plugins(repo_root: Path, meta: dict) -> int:
    """Write every target's plugin.json + marketplace.json from meta.

    Idempotent: always writes the full set and returns its size.
    """
    files = generated_plugin_files(meta)
    for rel, text in files.items():
        path = repo_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return len(files)


def check_meta_skill_coverage(repo_root: Path, meta: dict) -> list[str]:
    """Every stable skill must have a plugin.meta.json entry, and vice versa.

    This is the coverage guard: add a skill under skills/ and forget to list it
    in plugin.meta.json (so it gets no plugin keyword) and this fails, instead
    of the keyword silently going missing from every target's plugin.json.
    """
    errors: list[str] = []
    meta_skills = meta.get("skills", {})
    disk_skills = {d.name for d in iter_skill_dirs(repo_root)}

    for name in sorted(disk_skills - set(meta_skills)):
        errors.append(
            f"Stable skill '{name}' has no entry in plugin.meta.json \"skills\". "
            'Add one with a "keyword" so it gets a plugin keyword.'
        )
    for name in sorted(set(meta_skills) - disk_skills):
        errors.append(
            f"plugin.meta.json \"skills\" lists '{name}' but skills/{name}/ does "
            "not exist. Remove the entry or restore the skill."
        )
    for name, entry in meta_skills.items():
        if not isinstance(entry, dict) or not entry.get("keyword"):
            errors.append(
                f'plugin.meta.json skills["{name}"] is missing a "keyword".'
            )
    return errors


def _check_generated_files(repo_root: Path, files: dict) -> list[str]:
    """Fail if any generated file drifts from its expected text.

    Two-stage like validate_manifest: same parsed content but different bytes ->
    a formatting message; different content (or unparseable) -> out-of-date.
    """
    errors: list[str] = []
    for rel, expected in files.items():
        path = repo_root / rel
        if not path.exists():
            errors.append(f"Missing generated file {rel}.")
            continue
        actual = path.read_text()
        if actual == expected:
            continue
        try:
            same_content = json.loads(actual) == json.loads(expected)
        except json.JSONDecodeError:
            same_content = False
        if same_content:
            errors.append(
                f"{rel} is not in canonical generated form (whitespace / key order)."
            )
        else:
            errors.append(f"{rel} is out of date with plugin.meta.json.")
    return errors


def check_generated_plugins(repo_root: Path, meta: dict) -> list[str]:
    """Fail if any generated plugin file drifts from what meta would produce."""
    return _check_generated_files(repo_root, generated_plugin_files(meta))


# ---------------------------------------------------------------------------
# Routing (prompt-router data + Cursor rule, generated from meta "routing")
# ---------------------------------------------------------------------------
#
# The product-skill routing table lives once in plugin.meta.json "routing".
# Both the prompt router's instruction (rendered into hooks/_routing_data.json,
# which the router loads) and the Cursor rule (rules/databricks-routing.mdc) are
# rendered from that single table, so the two routing tables cannot drift.

def _routing_rows(meta: dict) -> list[str]:
    """The shared product-skill table rows ('- <label> -> <skill><note>')."""
    return [
        f"- {row['label']} -> {row['skill']}{row.get('note', '')}"
        for row in meta["routing"]["table"]
    ]


def render_routing_instruction(meta: dict) -> str:
    """The full UserPromptSubmit instruction the router injects (preamble + table + closing)."""
    routing = meta["routing"]
    rows = "".join(row + "\n" for row in _routing_rows(meta))
    return routing["instruction_preamble"] + "\n" + rows + routing["instruction_closing"]


def render_routing_rule(meta: dict) -> str:
    """The Cursor Apply-Intelligently rule (rules/databricks-routing.mdc) text."""
    routing = meta["routing"]
    preamble = "\n".join(routing["rule_preamble"])
    closing = "\n".join(routing["rule_closing"])
    rows = "\n".join(_routing_rows(meta))
    return (
        "---\n"
        f"description: {routing['rule_description']}\n"
        "alwaysApply: false\n"
        "---\n"
        "\n"
        f"{preamble}\n"
        "\n"
        f"{rows}\n"
        "\n"
        f"{closing}\n"
    )


def build_routing_data(meta: dict) -> dict:
    """The hooks/_routing_data.json payload the router loads (fail-open)."""
    routing = meta["routing"]
    return {
        "//": (
            'GENERATED FILE: do not edit. Rendered from plugin.meta.json "routing" '
            "by scripts/skills.py. Run `python3 scripts/skills.py generate`."
        ),
        "strong": routing["strong"],
        "ambiguous": routing["ambiguous"],
        "suppress": routing["suppress"],
        "instruction": render_routing_instruction(meta),
        "reminder": routing["reminder"],
    }


# Marker for the rules/ directory. databricks-routing.mdc is generated, but the
# .mdc itself cannot carry a "do not edit" note (its whole body is injected into
# the agent as the routing rule), so this sibling README is the signal. (The
# generated hooks/_routing_data.json carries its own "//" header instead.)
_ROUTING_RULE_README = """\
<!-- GENERATED FILE: do not edit by hand. -->

# Generated Cursor routing rule

`databricks-routing.mdc` in this directory is generated from the repo-root
`plugin.meta.json` (the `routing` block) by `scripts/skills.py`, alongside the
prompt router's `hooks/_routing_data.json`, so the two routing tables stay in
sync. To change routing, edit `plugin.meta.json` and run
`python3 scripts/skills.py generate`. CI fails on any drift. See `CONTRIBUTING.md`.
"""


def generated_routing_files(meta: dict) -> dict:
    """Map the generated routing files (repo-relative path -> canonical text)."""
    return {
        "hooks/_routing_data.json": json.dumps(build_routing_data(meta), indent=2) + "\n",
        "rules/databricks-routing.mdc": render_routing_rule(meta),
        "rules/README.md": _ROUTING_RULE_README,
    }


def generate_routing(repo_root: Path, meta: dict) -> int:
    """Write the prompt-router data + Cursor rule from meta. Idempotent."""
    files = generated_routing_files(meta)
    for rel, text in files.items():
        path = repo_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return len(files)


def check_generated_routing(repo_root: Path, meta: dict) -> list[str]:
    """Fail if the generated routing files drift from what meta would produce."""
    return _check_generated_files(repo_root, generated_routing_files(meta))


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


def _skill_parent(skill_dir: Path) -> str | None:
    """The `parent:` declared in a skill's SKILL.md frontmatter, or None."""
    frontmatter = _read_frontmatter(skill_dir / "SKILL.md")
    if not frontmatter:
        return None
    match = re.search(r"^parent:\s*(\S+)", frontmatter, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip('"').strip("'")


def check_routing_coverage(repo_root: Path, meta: dict) -> list[str]:
    """Every stable product skill must have a routing table row.

    A skill needs routing if it is top-level (no parent) or sits directly under
    databricks-core, excluding databricks-core itself. Skills nested under
    another product skill (e.g. databricks-app-design, parent databricks-apps)
    are reached via their parent and are exempt by derivation. This is the
    coverage guard #151's check_routing_tables does not add (that one checks the
    two tables agree and reference real skills, not that every product skill is
    listed).
    """
    errors: list[str] = []
    table_skills = {row["skill"] for row in meta.get("routing", {}).get("table", [])}
    for skill_dir in iter_skill_dirs(repo_root):
        name = skill_dir.name
        if name == "databricks-core":
            continue
        parent = _skill_parent(skill_dir)
        if parent in (None, "databricks-core") and name not in table_skills:
            errors.append(
                f"Stable skill '{name}' (parent {parent or 'none'}) has no routing row "
                'in plugin.meta.json "routing"."table"; add one so the prompt router '
                "and the Cursor rule can steer prompts to it."
            )
    return errors


def check_routing_patterns(repo_root: Path, meta: dict) -> list[str]:
    """Every routing regex in plugin.meta.json must compile.

    The strong/ambiguous/suppress patterns round-trip through JSON into
    hooks/_routing_data.json, which the router compiles at import. A bad pattern
    would pass generate and the (text-only) drift check yet crash the router in
    a real install, silently disabling all routing. Compiling them here makes a
    bad pattern fail CI first. (The router also degrades to its fallback on a
    bad pattern, but this catches it before it ever ships.)
    """
    errors: list[str] = []
    routing = meta.get("routing", {})
    for bucket in ("strong", "ambiguous", "suppress"):
        for pattern in routing.get(bucket, []):
            try:
                re.compile(pattern)
            except (re.error, TypeError) as exc:
                errors.append(
                    f'plugin.meta.json "routing"."{bucket}" pattern {pattern!r} '
                    f"is not a valid regex: {exc}"
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

    claude_path = repo_root / ".claude-plugin" / "plugin.json"
    try:
        claude_version = json.loads(claude_path.read_text()).get("version")
    except Exception:
        claude_version = None
    if claude_version and plugin.get("version") != claude_version:
        errors.append(
            f'.codex-plugin/plugin.json version ({plugin.get("version")}) must match '
            f".claude-plugin/plugin.json ({claude_version}); both are generated from "
            'plugin.meta.json "version" -- run `python3 scripts/skills.py generate`.'
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

    claude_path = repo_root / ".claude-plugin" / "plugin.json"
    try:
        claude_version = json.loads(claude_path.read_text()).get("version")
    except Exception:
        claude_version = None
    if claude_version and plugin.get("version") != claude_version:
        errors.append(
            f'.github/plugin/plugin.json version ({plugin.get("version")}) must match '
            f".claude-plugin/plugin.json ({claude_version}); both are generated from "
            'plugin.meta.json "version" -- run `python3 scripts/skills.py generate`.'
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

            meta = load_meta(repo_root)
            written_plugins = generate_plugins(repo_root, meta)
            print(
                f"Generated {written_plugins} plugin manifest file(s) from {META_FILE}"
            )

            written_routing = generate_routing(repo_root, meta)
            print(
                f"Generated {written_routing} routing file(s) from {META_FILE}"
            )

            written_hooks = generate_hooks(repo_root, meta)
            print(
                f"Generated {written_hooks} hook-wiring file(s) from {META_FILE}"
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

            try:
                meta = load_meta(repo_root)
            except (OSError, json.JSONDecodeError) as exc:
                print(
                    f"ERROR: cannot read {META_FILE} (the plugin source of truth): {exc}",
                    file=sys.stderr,
                )
                meta = None
                ok = False

            if meta is not None:
                coverage_errors = check_meta_skill_coverage(repo_root, meta)
                if coverage_errors:
                    print(
                        f"ERROR: {META_FILE} \"skills\" is out of sync with skills/:",
                        file=sys.stderr,
                    )
                    for err in coverage_errors:
                        print(f"  - {err}", file=sys.stderr)
                    ok = False

                drift_errors = check_generated_plugins(repo_root, meta)
                if drift_errors:
                    print(
                        "ERROR: generated plugin manifests are out of date with "
                        f"{META_FILE}:",
                        file=sys.stderr,
                    )
                    for err in drift_errors:
                        print(f"  - {err}", file=sys.stderr)
                    ok = False

                routing_drift = check_generated_routing(repo_root, meta)
                if routing_drift:
                    print(
                        "ERROR: generated routing files are out of date with "
                        f"{META_FILE}:",
                        file=sys.stderr,
                    )
                    for err in routing_drift:
                        print(f"  - {err}", file=sys.stderr)
                    ok = False

                routing_coverage = check_routing_coverage(repo_root, meta)
                if routing_coverage:
                    print(
                        "ERROR: a stable product skill is missing a routing row in "
                        f"{META_FILE}:",
                        file=sys.stderr,
                    )
                    for err in routing_coverage:
                        print(f"  - {err}", file=sys.stderr)
                    ok = False

                pattern_errors = check_routing_patterns(repo_root, meta)
                if pattern_errors:
                    print(
                        f"ERROR: a routing regex in {META_FILE} does not compile "
                        "(it would crash the prompt router in a real install):",
                        file=sys.stderr,
                    )
                    for err in pattern_errors:
                        print(f"  - {err}", file=sys.stderr)
                    ok = False

                hook_drift = check_generated_hooks(repo_root, meta)
                if hook_drift:
                    print(
                        "ERROR: generated hook-wiring files are out of date with "
                        f"{META_FILE}:",
                        file=sys.stderr,
                    )
                    for err in hook_drift:
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

            cursor_errors = check_cursor_plugin(repo_root)
            if cursor_errors:
                print(
                    "ERROR: .cursor-plugin manifest / components are misconfigured:",
                    file=sys.stderr,
                )
                for err in cursor_errors:
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

            routing_errors = check_routing_tables(repo_root)
            if routing_errors:
                print(
                    "ERROR: routing tables (router + Cursor rule) are out of sync:",
                    file=sys.stderr,
                )
                for err in routing_errors:
                    print(f"  - {err}", file=sys.stderr)
                ok = False

            if not ok:
                print(
                    "\nRun `python3 scripts/skills.py generate` to regenerate "
                    "manifest.json and every target's plugin.json + marketplace.json "
                    f"from {META_FILE}, then commit the result. For coverage errors, "
                    f"add the missing skill to {META_FILE} \"skills\" first.",
                    file=sys.stderr,
                )
                sys.exit(1)

            print("Everything is up to date.")


if __name__ == "__main__":
    main()
