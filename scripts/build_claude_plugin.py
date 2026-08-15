#!/usr/bin/env python3
"""Build a complete Claude plugin source snapshot."""

import argparse
import shutil
from pathlib import Path

from plugin_build import generated_provider_plugin


def build_claude_plugin(
    source_root: Path,
    output_directory: Path,
) -> None:
    """Generate and copy the complete Claude provider artifact."""
    with generated_provider_plugin(source_root, "claude") as (_, generated_plugin):
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
