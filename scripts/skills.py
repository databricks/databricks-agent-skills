#!/usr/bin/env python3
"""Façade for the skillsgen package.

The generator implementation lives in scripts/skillsgen/. This thin module
stays at scripts/skills.py so every entry point keeps working unchanged: the
`python3 scripts/skills.py {sync,generate,validate}` CLI, `import skills` from
scripts/bump_version.py, and the tests that load it by path via
importlib.util.spec_from_file_location("skills", ...). It re-exports the full
package API and delegates the CLI to skillsgen.cli.main.
"""

import sys
from pathlib import Path

# spec_from_file_location (the test loader) does not put this file's directory
# on sys.path, so `import skillsgen` would fail. Add scripts/ before importing
# the package. Harmless duplicate when run as a script or imported as a sibling.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skillsgen.common import (
    BUNDLE_DIR,
    META_FILE,
    load_meta,
    _serialize_plugin_json,
    _check_generated_files,
    _norm_rel_path,
    _read_frontmatter,
)
from skillsgen.discovery import (
    SHARED_ASSETS,
    STABLE_REPO_DIR,
    EXPERIMENTAL_REPO_DIR,
    iter_skill_dirs,
    iter_experimental_skill_dirs,
    extract_version_from_skill,
    iter_skill_files,
    iter_all_skill_dirs,
    _BLOCK_SCALAR_INDICATORS,
    extract_description_from_skill,
    _SHORT_DESC_MARKERS,
    synthesize_short_description,
    DISPLAY_NAME_OVERRIDES,
    synthesize_openai_yaml,
    ensure_codex_metadata,
    check_codex_metadata,
)
from skillsgen.manifest import (
    generate_manifest,
    _add_skill,
    _build_stable_entry,
    _build_experimental_entry,
    serialize_manifest,
    validate_manifest,
)
from skillsgen.plugins import (
    _CLAUDE_MARKETPLACE_SCHEMA,
    build_keywords,
    build_claude_plugin,
    build_codex_plugin,
    build_copilot_plugin,
    build_cursor_plugin,
    build_claude_marketplace,
    build_copilot_marketplace,
    build_codex_marketplace,
    build_cursor_marketplace,
    marketplace_ref,
    _scoped_sources,
    _GENERATED_README,
    _GENERATED_MANIFEST_DIRS,
    generated_plugin_files,
    generate_plugins,
    check_meta_skill_coverage,
    check_generated_plugins,
    check_scoped_sources,
)
from skillsgen.bundle import (
    PROVIDERS,
    _provider_specs,
    _is_noise,
    _iter_copy,
    _provider_hook_files,
    expected_bundle,
    generate_bundle,
    _iter_disk_bundle_files,
    check_generated_bundle,
)
from skillsgen.commands import (
    COMMANDS_SRC_DIR,
    iter_command_sources,
    render_command_files,
    check_command_templates,
)
from skillsgen.routing import (
    _routing_rows,
    render_routing_instruction,
    render_routing_rule,
    build_routing_data,
    _ROUTING_RULE_README,
    generated_routing_files,
    generate_routing,
    check_generated_routing,
    _skill_parent,
    check_routing_coverage,
    check_routing_patterns,
)
from skillsgen.hooks import (
    _hook_scripts,
    _nested_command,
    build_nested_hooks,
    build_copilot_hooks,
    build_cursor_hooks,
    generated_hook_files,
    generate_hooks,
    check_generated_hooks,
    check_no_orphan_hook_scripts,
    _UNWIRED_HOOK_SCRIPTS,
)
from skillsgen.validators import (
    _HOOK_SCRIPT_RE,
    _CLAUDE_EVENTS,
    _CODEX_EVENTS,
    _CURSOR_EVENTS,
    _COPILOT_EVENTS,
    _check_hook_event_names,
    check_plugin_components,
    check_skill_frontmatter,
    _HOOK_PY_RE,
    _check_hook_wiring,
    check_cursor_plugin,
    check_codex_plugin,
    check_copilot_plugin,
    _routing_skill_refs,
    _load_routing_instruction,
    check_routing_tables,
)
from skillsgen.generate import generate_all
from skillsgen.cli import main


if __name__ == "__main__":
    main()
