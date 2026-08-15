"""Generate provider plugin artifacts from the canonical skills generator."""

import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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


@contextmanager
def generated_provider_plugin(
    source_root: Path,
    provider: str,
) -> Iterator[tuple[Path, Path]]:
    """Yield the generated repository and provider plugin."""
    with tempfile.TemporaryDirectory(prefix="databricks-agent-skills-") as temporary:
        working_root = Path(temporary) / "databricks-agent-skills"
        shutil.copytree(source_root, working_root)
        _make_writable(working_root)

        generate_all(
            working_root,
            version_override=UNRELEASED_PLUGIN_VERSION,
        )
        plugin_directory = working_root / "plugins" / "databricks" / provider
        if not plugin_directory.is_dir():
            message = f"The generator did not produce {plugin_directory}."
            raise RuntimeError(message)
        yield working_root, plugin_directory
