#!/usr/bin/env python3
"""Build a complete provider plugin source snapshot."""

import argparse
import shutil
from pathlib import Path

from plugin_build import generated_provider_plugin
from skillsgen.bundle import PROVIDERS


def build_provider_plugin(
    source_root: Path,
    output_directory: Path,
    provider: str,
) -> None:
    """Generate and copy the complete provider artifact."""
    with generated_provider_plugin(source_root, provider) as (_, generated_plugin):
        if output_directory.exists():
            shutil.rmtree(output_directory)
        shutil.copytree(generated_plugin, output_directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--source-marker", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_marker = Path(args.source_marker)
    source_root = source_marker.parent.parent
    build_provider_plugin(source_root, Path(args.output), args.provider)


if __name__ == "__main__":
    main()
