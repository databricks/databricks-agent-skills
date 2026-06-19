"""Render per-provider slash-command files from one templated source.

`commands/<name>.md` is the single source for each command. The Claude/Codex
form and the Cursor form differ in three ways (frontmatter fields, `$1`-vs-prose
argument phrasing, and `:`-vs-`-` command namespacing), so the source uses an
inline alternation token:

    {{ claude-or-codex text | cursor text }}

The renderer picks the left side for Claude/Codex and the right side for Cursor.
Literal `|` outside `{{...}}` (e.g. a Markdown table) is left untouched. Each
provider's rendered file is written into that provider's bundle folder by
skillsgen.bundle (Claude: `<name>.md`; Cursor: `databricks-<name>.md`). Codex and
Copilot ship no commands, so only Claude and Cursor are rendered. Stdlib-only.
"""

import re
from pathlib import Path

COMMANDS_SRC_DIR = "commands"
# Cursor namespaces commands by filename prefix (the `/databricks-doctor` form);
# Claude namespaces by plugin (`/databricks:doctor`), so its file is bare.
_CURSOR_PREFIX = "databricks-"
_ALT_RE = re.compile(r"\{\{(.*?)\|(.*?)\}\}", re.S)


def _render(text: str, cursor: bool) -> str:
    """Resolve every {{a|b}} alternation: left for Claude/Codex, right for Cursor."""
    return _ALT_RE.sub(lambda m: m.group(2) if cursor else m.group(1), text)


def iter_command_sources(repo_root: Path):
    """Yield the templated command source files under commands/."""
    src = repo_root / COMMANDS_SRC_DIR
    if not src.is_dir():
        return
    yield from sorted(src.glob("*.md"))


def render_command_files(repo_root: Path, provider: str) -> dict:
    """Map each command's rendered filename -> text for a provider.

    provider is "claude" or "cursor" (Codex/Copilot ship no commands). Cursor
    files are prefixed `databricks-`; Claude files keep the bare source name.
    """
    cursor = provider == "cursor"
    out = {}
    for md in iter_command_sources(repo_root):
        name = (_CURSOR_PREFIX + md.name) if cursor else md.name
        out[name] = _render(md.read_text(), cursor)
    return out


def check_command_templates(repo_root: Path) -> list[str]:
    """Fail if a command template is malformed (it would render broken commands)."""
    errors: list[str] = []
    for md in iter_command_sources(repo_root):
        text = md.read_text()
        if text.count("{{") != text.count("}}"):
            errors.append(f"commands/{md.name}: unbalanced '{{{{'/'}}}}' alternation tokens.")
        for m in re.finditer(r"\{\{(.*?)\}\}", text, re.S):
            if "|" not in m.group(1):
                errors.append(
                    f"commands/{md.name}: alternation token is missing the '|' separator."
                )
        for cursor in (False, True):
            if not _render(text, cursor).lstrip().startswith("---"):
                side = "cursor" if cursor else "claude"
                errors.append(
                    f"commands/{md.name}: rendered {side} output has no YAML frontmatter."
                )
    return errors
