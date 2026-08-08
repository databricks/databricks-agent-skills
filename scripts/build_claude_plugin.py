#!/usr/bin/env python3
"""Build a complete Claude plugin source snapshot."""

import argparse
import os
import shutil
import stat
import tempfile
from pathlib import Path

from skillsgen.generate import generate_all


# Universe excludes public release state from its source mirror. This SemVer
# marks local artifacts as unreleased without constraining marketplace releases.
UNRELEASED_PLUGIN_VERSION = "0.0.0-unreleased"


def _make_writable(root: Path) -> None:
    """Make the copied source tree writable for generation."""
    root.chmod(root.stat().st_mode | stat.S_IWUSR)
    for directory, directory_names, file_names in os.walk(root):
        for name in directory_names + file_names:
            path = Path(directory) / name
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def build_claude_plugin(
    source_root: Path,
    output_directory: Path,
) -> None:
    """Generate and copy the complete Claude provider artifact."""
    with tempfile.TemporaryDirectory(prefix="databricks-agent-skills-") as temporary:
        working_root = Path(temporary) / "databricks-agent-skills"
        shutil.copytree(source_root, working_root)
        _make_writable(working_root)

        generate_all(
            working_root,
            version_override=UNRELEASED_PLUGIN_VERSION,
        )
        generated_plugin = working_root / "plugins" / "databricks" / "claude"
        if not generated_plugin.is_dir():
            message = f"The generator did not produce {generated_plugin}."
            raise RuntimeError(message)
        if output_directory.exists():
            shutil.rmtree(output_directory)
        shutil.copytree(generated_plugin, output_directory)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-marker", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_marker = Path(args.source_marker)
    source_root = source_marker.parent.parent
    build_claude_plugin(source_root, Path(args.output))


if __name__ == "__main__":
    main()
