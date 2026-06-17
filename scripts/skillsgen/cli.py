"""Command-line entry point for the skills generator (sync / generate / validate)."""

import argparse
import json
import sys
from pathlib import Path

from skillsgen.common import META_FILE, load_meta
from skillsgen.discovery import check_codex_metadata, ensure_codex_metadata
from skillsgen.manifest import generate_manifest, serialize_manifest, validate_manifest
from skillsgen.plugins import (
    check_generated_plugins,
    check_meta_skill_coverage,
    generate_plugins,
)
from skillsgen.routing import (
    check_generated_routing,
    check_routing_coverage,
    check_routing_patterns,
    generate_routing,
)
from skillsgen.hooks import (
    check_generated_hooks,
    check_no_orphan_hook_scripts,
    generate_hooks,
)
from skillsgen.validators import (
    check_codex_plugin,
    check_copilot_plugin,
    check_cursor_plugin,
    check_plugin_components,
    check_routing_tables,
)


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
    repo_root = Path(__file__).resolve().parent.parent.parent

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

                orphan_hooks = check_no_orphan_hook_scripts(repo_root, meta)
                if orphan_hooks:
                    print(
                        f"ERROR: orphaned hook script(s) not wired into {META_FILE} "
                        '"hooks":',
                        file=sys.stderr,
                    )
                    for err in orphan_hooks:
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
