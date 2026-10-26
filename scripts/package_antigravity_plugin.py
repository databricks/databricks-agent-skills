#!/usr/bin/env python3
"""Package the generated Antigravity plugin for extraction and local installation."""

import argparse
from pathlib import Path
import zipfile


def package_antigravity_plugin(plugin_root: Path, output_path: Path) -> None:
    """Write a reproducible ZIP with plugin.json at its root."""
    if output_path.resolve().is_relative_to(plugin_root.resolve()):
        raise ValueError("The archive output must be outside the plugin directory.")
    if not (plugin_root / "plugin.json").is_file():
        raise ValueError("Missing plugin manifest: plugin.json")

    paths = sorted(plugin_root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("Plugin archives must contain regular files, not symlinks.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if not path.is_file():
                continue
            # Fixed timestamps and permissions keep release archives independent
            # of checkout time and runner umask.
            info = zipfile.ZipInfo(path.relative_to(plugin_root).as_posix())
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        package_antigravity_plugin(args.plugin_root, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
