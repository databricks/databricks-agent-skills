#!/usr/bin/env python3
"""Build an installable local marketplace for the complete Codex plugin."""

import argparse
import json
import shutil
from pathlib import Path

from plugin_build import generated_provider_plugin


def build_codex_plugin(
    source_root: Path,
    output_directory: Path,
) -> None:
    """Generate the Codex provider artifact and its local marketplace."""
    with generated_provider_plugin(source_root, "codex") as (
        working_root,
        generated_plugin,
    ):
        if output_directory.exists():
            shutil.rmtree(output_directory)

        plugin_directory = output_directory / "plugin"
        shutil.copytree(generated_plugin, plugin_directory)

        marketplace_path = working_root / ".agents" / "plugins" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list) or len(plugins) != 1:
            raise RuntimeError("The generated Codex marketplace must contain one plugin.")
        plugins[0]["source"] = {
            "source": "local",
            "path": "./plugin",
        }

        output_marketplace_path = (
            output_directory / ".agents" / "plugins" / "marketplace.json"
        )
        output_marketplace_path.parent.mkdir(parents=True)
        output_marketplace_path.write_text(
            json.dumps(marketplace, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-marker", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_marker = Path(args.source_marker)
    source_root = source_marker.parent.parent
    build_codex_plugin(source_root, Path(args.output))


if __name__ == "__main__":
    main()
