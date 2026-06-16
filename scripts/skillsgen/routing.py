"""Prompt-router data and Cursor rule generation from the meta routing block."""

import json
import re
from pathlib import Path

from skillsgen.common import _check_generated_files, _read_frontmatter
from skillsgen.discovery import iter_skill_dirs


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
            'GENERATED FILE: do not edit. Rendered from metaplugin/plugin.meta.json '
            '"routing" by scripts/skills.py. Run `python3 scripts/skills.py generate`.'
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

`databricks-routing.mdc` in this directory is generated from
`metaplugin/plugin.meta.json` (the `routing` block) by `scripts/skills.py`,
alongside the prompt router's `hooks/_routing_data.json`, so the two routing
tables stay in sync. To change routing, edit `metaplugin/plugin.meta.json` and run
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
