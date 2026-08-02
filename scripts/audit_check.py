#!/usr/bin/env python3
"""Audit gate for the skill corpus: one reproducible count per finding ID.

`scripts/skills.py validate` checks the *plumbing* (manifest, bundle, plugin
manifests, hook wiring). Nothing there looks at skill **content**. This module
is the content-side counterpart: it reproduces the remediation audit's
per-finding numbers so that "is this finding fixed?" is a count, not a
judgement call.

Usage::

    python3 scripts/audit_check.py                 # every finding, rollup table
    python3 scripts/audit_check.py --only PD-5     # one finding, exit 0 when clean
    python3 scripts/audit_check.py --only PD-5 --details

Exit status is 0 when every *selected* must-fix finding is at zero. Advisory,
rollup, and blocked findings are reported but never fail the run unless they
are named explicitly with `--only`.

House rules this file follows (same as `scripts/skillsgen/`):

- **Stdlib only.** The protected CI runner cannot reach pypi, so no PyYAML.
  Frontmatter is read with regexes, exactly as `validators.py` does.
- **No `raise`, no `assert`.** Every `check_*` returns `list[str]` and lets the
  caller print. An empty list means the finding is at zero.

Counting conventions (each was measured against the corpus before being fixed
here; changing one changes every number below):

- **D6 — token/line basis.** Frontmatter is stripped with ``^---\\n.*?\\n---\\n``;
  the body is everything after. ``lines = len(body.rstrip("\\n").split("\\n"))``
  and ``tokens = round(len(body) / 4)``. Floor division instead of ``round`` is
  what produces off-by-one drift against the audit's figures.
- **D9 — the `../` matcher excludes `...` ellipsis.** A naive ``\\.\\./`` also
  matches truncation markers such as ``/Volumes/.../file.csv``. The lookbehind
  in `_TRAVERSAL_RE` drops those; without it every traversal class over-reports
  and a sweep would corrupt placeholder paths.
- **D1 — fenced code is exempt.** `../` inside a fence is overwhelmingly a
  working example (DAB `notebook_path:` values, TypeScript imports). Fences are
  blanked line-for-line, so reported line numbers still match the file.
- **D7 — traversals are classified by intent, not by resolution.** If the
  target's first non-`..` segment (after an optional `skills/` or
  `experimental/`) names a sibling skill, it is cross-skill wherever it happens
  to resolve. Non-existence is reported separately as NEW-A.
- **D8 — a reference "has a TOC"** when a `Table of Contents`/`Contents`/`TOC`
  heading, or >= 3 `](#` anchor links, appear in the first 60 body lines.
- **D3 — reference-to-reference** is a markdown link from a file under
  `references/` to another `.md` resolving inside the same `references/` tree,
  excluding self-links and fenced blocks.
"""

import argparse
import re
import sys
from pathlib import Path

# spec_from_file_location-style loaders do not put this file's directory on
# sys.path, so `import skillsgen` would fail. Same guard as scripts/skills.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skillsgen.discovery import (  # noqa: E402  (path guard must run first)
    extract_description_from_skill,
    iter_all_skill_dirs,
    iter_skill_dirs,
)


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
# D9: a traversal, but not the tail of an "..." ellipsis and not "a../".
_TRAVERSAL_RE = re.compile(r"(?<![.\w])\.\./")
# The same traversal, but only where it spells out a path to a `.md` file. This
# is what separates a prose *reference* to another file from prose *about*
# traversal ("cannot contain `../`", a `%run ../path` warning, a DAB
# `../src/notebooks/extract.py` value) — none of which names a `.md`.
_PROSE_TRAVERSAL_RE = re.compile(r"(?<![.\w])\.\./[\w./-]*\.md")
# Markdown inline link. The optional trailing "title" form is rare here but
# cheap to tolerate; angle-bracket targets are not used in this corpus.
_LINK_RE = re.compile(r"\[([^\]\n]*)\]\(\s*([^)\s]+?)(?:\s+\"[^\"]*\")?\s*\)")
_FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


def iter_md_files(skill_dir: Path):
    """Yield every markdown file in a skill, skipping generated metadata dirs."""
    for path in sorted(skill_dir.rglob("*.md")):
        rel_parts = path.relative_to(skill_dir).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if rel_parts[0] in ("agents", "assets"):
            continue
        yield path


def iter_reference_files(skill_dir: Path):
    """Yield a skill's reference content: `references/**` *and* the skill root.

    Root-level `.md` files (NEW-C) are reference content that happens to sit in
    the wrong place. Scoping this to `references/` only is precisely the bug
    NEW-C describes — those four files would silently escape the TOC and orphan
    checks — so they are included here and reported separately by `check_new_c`.
    """
    references = skill_dir / "references"
    if references.is_dir():
        yield from sorted(references.rglob("*.md"))
    for path in sorted(skill_dir.glob("*.md")):
        if path.name != "SKILL.md":
            yield path


def skill_body(text: str) -> str:
    """Return the SKILL.md/reference body with YAML frontmatter removed (D6)."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def body_lines(body: str) -> int:
    """Line count under the D6 convention."""
    return len(body.rstrip("\n").split("\n"))


def body_tokens(body: str) -> int:
    """Token estimate under the D6 convention: characters / 4, rounded."""
    return round(len(body) / 4)


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering (D1).

    Both ``` and ~~~ fences are handled, indented or language-tagged. Lines
    inside a fence become empty strings rather than disappearing, so a match's
    line number still points at the right line of the real file.
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)[0]
                out.append("")
            else:
                out.append(line)
        else:
            out.append("")
            if match and match.group(1)[0] == fence:
                fence = None
    return "\n".join(out)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def rel(repo_root: Path, path: Path) -> str:
    return str(path.relative_to(repo_root))


def link_target(target: str) -> str:
    """Strip a trailing anchor from a markdown link target."""
    return target.split("#", 1)[0]


def is_external(target: str) -> bool:
    return bool(re.match(r"^(https?:|mailto:|ftp:|#)", target))


def frontmatter_of(text: str) -> str:
    match = _FRONTMATTER_RE.match(text)
    return match.group(0) if match else ""


def frontmatter_value(text: str, key: str) -> str | None:
    """Read a scalar frontmatter field. Stdlib-only, like validators.py."""
    match = re.search(
        rf"^{re.escape(key)}:\s*(.*?)\s*$", frontmatter_of(text), re.MULTILINE
    )
    if not match:
        return None
    return match.group(1).strip().strip('"').strip("'")


def skill_names(repo_root: Path) -> set[str]:
    return {d.name for d in iter_all_skill_dirs(repo_root)}


# ---------------------------------------------------------------------------
# SPEC-10a — `../` traversal, split into its four classes
# ---------------------------------------------------------------------------

def _classify_traversal(target: str, names: set[str]) -> str:
    """cross vs intra, by intent (D7)."""
    segments = [s for s in link_target(target).split("/") if s]
    while segments and segments[0] == "..":
        segments.pop(0)
    if segments and segments[0] in ("skills", "experimental"):
        segments.pop(0)
    if segments and segments[0] in names:
        return "cross"
    return "intra"


def _scan_traversals(repo_root: Path) -> dict[str, list[str]]:
    """One pass over the corpus; returns violations keyed by traversal class.

    Classes: ``cross`` and ``intra`` (link targets, per D7), ``prose`` (a `../`
    path to a `.md` file outside any link and outside a fence), ``dangling``
    (a relative link target that does not exist on disk), and ``fence``
    (reported for context only — these are working examples, not defects).
    """
    names = skill_names(repo_root)
    found: dict[str, list[str]] = {
        "cross": [], "intra": [], "prose": [], "dangling": [], "fence": [],
        "self_parent": []
    }

    for skill_dir in iter_all_skill_dirs(repo_root):
        for path in iter_md_files(skill_dir):
            raw = read_text(path)
            stripped = strip_fences(raw)
            where = rel(repo_root, path)

            raw_lines = raw.split("\n")
            stripped_lines = stripped.split("\n")
            for lineno, (raw_line, clean_line) in enumerate(
                zip(raw_lines, stripped_lines), start=1
            ):
                if clean_line:
                    continue
                for _ in _TRAVERSAL_RE.finditer(raw_line):
                    found["fence"].append(f"{where}:{lineno}: in-fence '../' (exempt)")

            for lineno, line in enumerate(stripped_lines, start=1):
                link_spans = []
                for match in _LINK_RE.finditer(line):
                    link_spans.append(match.span())
                    target = match.group(2)
                    if is_external(target):
                        continue
                    if _TRAVERSAL_RE.search(target):
                        kind = _classify_traversal(target, names)
                        found[kind].append(
                            f"{where}:{lineno}: {kind}-skill '../' link -> {target}"
                        )
                    resolved = (path.parent / link_target(target)).resolve()
                    if link_target(target).endswith(".md") and not resolved.exists():
                        found["dangling"].append(
                            f"{where}:{lineno}: link target does not exist -> {target}"
                        )

                # Prose: a `../` path naming a .md file, outside any link span.
                # Link *text* that repeats the target ("[../x.md](../x.md)") is
                # excluded here — it disappears when the link itself is fixed,
                # so counting it would bill the same defect to two classes.
                for match in _PROSE_TRAVERSAL_RE.finditer(line):
                    if any(s <= match.start() < e for s, e in link_spans):
                        continue
                    # D8: `../SKILL.md` from a references/ file names its own
                    # parent. The path never leaves the skill directory, so no
                    # subset install can break it -- the sole rationale for the
                    # SPEC-10a class. Reported for context, never a defect.
                    if link_target(match.group(0)).lstrip("`") == "../SKILL.md":
                        found["self_parent"].append(
                            f"{where}:{lineno}: self-parent '../SKILL.md' (exempt)"
                        )
                        continue
                    found["prose"].append(
                        f"{where}:{lineno}: '../' path in prose -> {match.group(0)}"
                    )

    return found


def check_spec_10a_cross(repo_root: Path) -> list[str]:
    """Cross-skill `../` links. Skills install as subsets; the path dangles."""
    return _scan_traversals(repo_root)["cross"]


def check_spec_10a_intra(repo_root: Path) -> list[str]:
    """`../` links that stay inside their own skill. Rewrite from the root."""
    return _scan_traversals(repo_root)["intra"]


def check_spec_10a_prose(repo_root: Path) -> list[str]:
    """`../<path>.md` written in prose rather than as a link."""
    return _scan_traversals(repo_root)["prose"]


def check_spec_10a_self_parent(repo_root: Path) -> list[str]:
    """`../SKILL.md` naming the skill's own parent. Exempt under D8."""
    return _scan_traversals(repo_root)["self_parent"]


def check_spec_10a_fence(repo_root: Path) -> list[str]:
    """In-fence `../` — reported for context, exempt under D1. Never a defect."""
    return _scan_traversals(repo_root)["fence"]


# NEW-B: `skills/databricks-apps/references/appkit/proto-first.md` links a
# `references/plugin-contracts.md` that exists nowhere in the repo, under any
# path. Which file it *meant* is a maintainer decision (filed as an issue), so
# it is excluded from NEW-A and reported on its own; guessing a target would
# ship a wrong pointer.
_NEW_B_TARGET = "plugin-contracts.md"


def check_new_a(repo_root: Path) -> list[str]:
    """Relative `.md` links that do not resolve on disk, NEW-B excluded."""
    return [
        v for v in _scan_traversals(repo_root)["dangling"]
        if _NEW_B_TARGET not in v
    ]


def check_new_b(repo_root: Path) -> list[str]:
    """The one dangling link whose intended target is unknowable. Advisory."""
    return [
        v for v in _scan_traversals(repo_root)["dangling"]
        if _NEW_B_TARGET in v
    ]


# ---------------------------------------------------------------------------
# SPEC-10b — bare-basename references
# ---------------------------------------------------------------------------

# One occurrence rule, three shapes. A `](...)`-only regex finds *zero* of the
# corpus's actual defects — they are backticked (`GOTCHAS.md`) or bold prose
# (**Read GOTCHAS.md**). Matching each shape with its own regex instead
# double-counts `**Read `x.md`**` and mis-captures the tail of a correctly
# prefixed link (`](references/x.md)` -> "x.md"), so this matches the *mention*
# once and only labels its shape. The lookbehind is what rejects a mention that
# already carries a directory prefix.
_BARE_BASENAME_RE = re.compile(r"(?<![\w./-])([A-Za-z0-9._-]+\.md)\b")


def _mention_shape(line: str, start: int) -> str:
    before = line[:start]
    if before.endswith("`"):
        return "backtick"
    if before.endswith("]("):
        return "link"
    return "prose"


def check_spec_10b(repo_root: Path) -> list[str]:
    """A `references/` file named by bare basename, with no `references/` prefix.

    A bare basename is a defect even when the file resolves by luck: the agent
    is told to read a path that is wrong relative to the skill root.

    Scoped to basenames that resolve *under `references/`*. A basename that
    resolves at the skill root is NEW-C instead — there the fix is to move the
    file, not to prefix the link, and counting it in both classes would make
    each report the other's work as outstanding.

    A basename inside a markdown link *label* is display text, not a path:
    `[1-widget-specifications.md#counter](references/1-widget-specifications.md#counter)`
    routes correctly and is not a defect. Only the path itself is checked.
    """
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        skill_md = skill_dir / "SKILL.md"
        text = strip_fences(read_text(skill_md))
        where = rel(repo_root, skill_md)
        for lineno, line in enumerate(text.split("\n"), start=1):
            labels = [m.span(1) for m in _LINK_RE.finditer(line)]
            for match in _BARE_BASENAME_RE.finditer(line):
                if any(s <= match.start() < e for s, e in labels):
                    continue
                basename = match.group(1)
                if basename == "SKILL.md":
                    continue
                targets = list(skill_dir.glob(f"references/**/{basename}"))
                if not targets:
                    continue
                shape = _mention_shape(line, match.start())
                violations.append(
                    f"{where}:{lineno}: bare basename ({shape}) '{basename}' "
                    f"resolves at {rel(skill_dir, targets[0])}"
                )
    return violations


# ---------------------------------------------------------------------------
# PD-5 / PD-5b — reference depth
# ---------------------------------------------------------------------------

def check_pd_5(repo_root: Path) -> list[str]:
    """A reference file linking to another reference file (D3).

    The second hop is invisible to a partial read, so the target is effectively
    unrouted even though a link exists.
    """
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        references = skill_dir / "references"
        if not references.is_dir():
            continue
        for path in sorted(references.rglob("*.md")):
            text = strip_fences(read_text(path))
            where = rel(repo_root, path)
            for lineno, line in enumerate(text.split("\n"), start=1):
                for match in _LINK_RE.finditer(line):
                    target = link_target(match.group(2))
                    if not target or is_external(match.group(2)):
                        continue
                    if not target.endswith(".md"):
                        continue
                    resolved = (path.parent / target).resolve()
                    if resolved == path.resolve():
                        continue
                    if references.resolve() not in resolved.parents:
                        continue
                    violations.append(
                        f"{where}:{lineno}: reference -> reference link -> {target}"
                    )
    return violations


def check_pd_5b(repo_root: Path) -> list[str]:
    """References must be one level deep: no `references/<dir>/file.md`."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        references = skill_dir / "references"
        if not references.is_dir():
            continue
        for path in sorted(references.rglob("*.md")):
            if len(path.relative_to(references).parts) > 1:
                violations.append(
                    f"{rel(repo_root, path)}: nested reference (references/ is "
                    "one level deep)"
                )
    return violations


# ---------------------------------------------------------------------------
# PD-6 — reference tables of contents
# ---------------------------------------------------------------------------

_TOC_HEADING_RE = re.compile(
    r"^#{1,6}\s+(Table of Contents|Contents|TOC)\b", re.MULTILINE | re.IGNORECASE
)
_TOC_WINDOW = 60
_TOC_ANCHOR_MIN = 3


def has_toc(body: str) -> bool:
    """D8: a TOC heading, or >= 3 anchor links, in the first 60 body lines."""
    window = "\n".join(body.split("\n")[:_TOC_WINDOW])
    if _TOC_HEADING_RE.search(window):
        return True
    return window.count("](#") >= _TOC_ANCHOR_MIN


def check_pd_6(repo_root: Path) -> list[str]:
    """Reference files over 100 lines must carry a table of contents."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        for path in iter_reference_files(skill_dir):
            body = skill_body(read_text(path))
            lines = body_lines(body)
            if lines <= 100 or has_toc(body):
                continue
            violations.append(f"{rel(repo_root, path)}: {lines} lines, no TOC")
    return violations


# ---------------------------------------------------------------------------
# PD-1 / PD-2 / PD-3 — SKILL.md ceilings
# ---------------------------------------------------------------------------

MAX_BODY_LINES = 500
MAX_BODY_TOKENS = 5000


def _ceiling_breaches(repo_root: Path) -> list[tuple[Path, int, int]]:
    sizes = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        body = skill_body(read_text(skill_dir / "SKILL.md"))
        sizes.append((skill_dir, body_lines(body), body_tokens(body)))
    return sizes


def check_pd_1(repo_root: Path) -> list[str]:
    """SKILL.md body under 500 lines (Level 2 of progressive disclosure)."""
    return [
        f"{rel(repo_root, d)}/SKILL.md: {lines} lines (limit {MAX_BODY_LINES})"
        for d, lines, _ in _ceiling_breaches(repo_root)
        if lines >= MAX_BODY_LINES
    ]


def check_pd_2(repo_root: Path) -> list[str]:
    """SKILL.md body under 5,000 tokens. Binds independently of the line cap."""
    return [
        f"{rel(repo_root, d)}/SKILL.md: {tokens} tokens (limit {MAX_BODY_TOKENS})"
        for d, _, tokens in _ceiling_breaches(repo_root)
        if tokens >= MAX_BODY_TOKENS
    ]


def check_pd_3(repo_root: Path) -> list[str]:
    """Rollup of PD-1 and PD-2: skills needing a split. Not summed into totals."""
    return [
        f"{rel(repo_root, d)}/SKILL.md: {lines} lines / {tokens} tokens"
        for d, lines, tokens in _ceiling_breaches(repo_root)
        if lines >= MAX_BODY_LINES or tokens >= MAX_BODY_TOKENS
    ]


# ---------------------------------------------------------------------------
# PD-4 — routing
# ---------------------------------------------------------------------------

_DEAD_SKILL_NAME = "databricks-spark-declarative-pipelines"


def check_pd_4a(repo_root: Path) -> list[str]:
    """Pointers to a skill name that does not exist (it is databricks-pipelines)."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        for path in iter_md_files(skill_dir):
            for lineno, line in enumerate(read_text(path).split("\n"), start=1):
                for _ in re.finditer(re.escape(_DEAD_SKILL_NAME), line):
                    violations.append(
                        f"{rel(repo_root, path)}:{lineno}: names a skill that "
                        f"does not exist: {_DEAD_SKILL_NAME}"
                    )
    return violations


def check_pd_4b(repo_root: Path) -> list[str]:
    """Every `parent: databricks-core` skill must be reachable from core."""
    core = repo_root / "skills" / "databricks-core" / "SKILL.md"
    if not core.exists():
        return [f"{rel(repo_root, core)} is missing; core cannot route anywhere."]
    routing = read_text(core)
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        if skill_dir.name == "databricks-core":
            continue
        parent = frontmatter_value(read_text(skill_dir / "SKILL.md"), "parent")
        if parent != "databricks-core":
            continue
        if skill_dir.name not in routing:
            violations.append(
                f"{rel(repo_root, core)}: declares parent databricks-core but is "
                f"not mentioned there: {skill_dir.name}"
            )
    return violations


def check_pd_4c(repo_root: Path) -> list[str]:
    """Reference files no SKILL.md points at, in any form."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        routing = read_text(skill_dir / "SKILL.md")
        for path in iter_reference_files(skill_dir):
            relative = str(path.relative_to(skill_dir))
            if relative in routing or path.name in routing:
                continue
            violations.append(
                f"{rel(repo_root, path)}: orphan (no SKILL.md link or mention)"
            )
    return violations


# ---------------------------------------------------------------------------
# NEW-C — reference content sitting at the skill root
# ---------------------------------------------------------------------------

def check_new_c(repo_root: Path) -> list[str]:
    """Reference-style `.md` files at a skill root instead of `references/`.

    They resolve on disk, so nothing looks broken — but every `references/`-
    scoped check (TOC, orphan, one-level-deep) skips them silently.
    """
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        for path in sorted(skill_dir.glob("*.md")):
            if path.name == "SKILL.md":
                continue
            violations.append(
                f"{rel(repo_root, path)}: reference file at the skill root "
                "(belongs under references/)"
            )
    return violations


# ---------------------------------------------------------------------------
# DESC-1 / DESC-3 — descriptions without trigger conditions
# ---------------------------------------------------------------------------

# A reviewed allowlist, deliberately not a regex gate over the whole corpus:
# "does this text state a condition" is a judgement call, and a when-clause
# regex flags 8-10 skills of which several are valid elided-object
# self-references ("Use to grant or revoke...", "Load this first for..."). These
# six were reviewed one by one; each states capability only.
_DESC_REVIEWED = (
    "databricks-agent-bricks",
    "databricks-vector-search",
    "databricks-execution-compute",
    "databricks-unstructured-pdf-generation",
    "databricks-genie-agents",
    "databricks-ai-functions",
)
_WHEN_CLAUSE_RE = re.compile(
    r"\b(use (this |these )?(skill )?(when|if|for requests|whenever)"
    r"|triggers? (on|when)|when the user|when you (need|are|want)"
    r"|whenever the user|invoke when|use for)\b",
    re.IGNORECASE,
)


def check_desc_1(repo_root: Path) -> list[str]:
    """The reviewed six descriptions, until each states a trigger condition."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        if skill_dir.name not in _DESC_REVIEWED:
            continue
        description = extract_description_from_skill(skill_dir)
        if _WHEN_CLAUSE_RE.search(description):
            continue
        violations.append(
            f"{rel(repo_root, skill_dir)}/SKILL.md: description states capability "
            f"only, no trigger condition ({len(description)} chars)"
        )
    return violations


def resident_set(repo_root: Path) -> tuple[int, int]:
    """(stable, all-in) token cost of every always-resident name+description."""
    stable = 0
    experimental = 0
    for parent, bucket in (("skills", "stable"), ("experimental", "experimental")):
        for skill_dir in iter_skill_dirs(repo_root, parent=parent):
            text = read_text(skill_dir / "SKILL.md")
            name = frontmatter_value(text, "name") or skill_dir.name
            description = extract_description_from_skill(skill_dir).replace('\\"', '"')
            chars = len(name) + len(description)
            if bucket == "stable":
                stable += chars
            else:
                experimental += chars
    return round(stable / 4), round((stable + experimental) / 4)


# ---------------------------------------------------------------------------
# TOK-5 — preview / beta markers
# ---------------------------------------------------------------------------

# Strict, parenthesised, case-sensitive. The broad case-insensitive variant
# counts 85-87 markers across 15 skills and the SKILL.md-only broad variant
# counts 27/9; neither matches the audit's 30/10 either. Until that definition
# is settled this reports the strict basis and stays advisory rather than
# sweeping the corpus against a number nobody can reproduce.
_PREVIEW_RE = re.compile(r"\((Public Preview|Private Preview|Beta)\)")


def check_tok_5(repo_root: Path) -> list[str]:
    """Bare inline preview/beta markers (strict basis; see D5)."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        for path in iter_md_files(skill_dir):
            for lineno, line in enumerate(read_text(path).split("\n"), start=1):
                for match in _PREVIEW_RE.finditer(line):
                    violations.append(
                        f"{rel(repo_root, path)}:{lineno}: uncontained marker "
                        f"{match.group(0)}"
                    )
    return violations


# ---------------------------------------------------------------------------
# Compatibility pins
# ---------------------------------------------------------------------------

_CLI_VERSION_RE = re.compile(r"\bv?\d+\.\d+\.\d+\b")
# A version literal only contradicts the pin when it is stated *as the CLI's*
# version. Skill bodies are full of SDK and library pins (mlflow, the Python
# SDK, plutoprint); requiring "CLI" within a short window ahead of the literal
# is what separates "Databricks CLI (>= v0.288.0)" from "SDK >= 0.85.0".
_CLI_VERSION_CLAIM_RE = re.compile(r"\bCLI\b.{0,40}?(v?\d+\.\d+\.\d+)\b", re.IGNORECASE)


def check_compat_1(repo_root: Path) -> list[str]:
    """Every skill should agree on one CLI floor, or justify its own.

    Blocked on a verified current Databricks CLI version: guessing one ships a
    wrong requirement to every user. The count is the number of *excess* shapes
    (distinct `compatibility` values, plus one pseudo-shape for skills that
    carry no field at all), so it reaches zero when a single shape remains.
    """
    shapes: dict[str, list[str]] = {}
    contradictions: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        text = read_text(skill_dir / "SKILL.md")
        value = frontmatter_value(text, "compatibility")
        shapes.setdefault(value if value is not None else "(absent)", []).append(
            skill_dir.name
        )
        pinned = {p.lstrip("v") for p in _CLI_VERSION_RE.findall(value or "")}
        if not pinned:
            continue
        # Body line numbers are frontmatter-relative; shift them back so the
        # report cites the line a reader would open the file to.
        offset = frontmatter_of(text).count("\n")
        for lineno, line in enumerate(skill_body(text).split("\n"), start=1):
            for found in _CLI_VERSION_CLAIM_RE.findall(line):
                if found.lstrip("v") not in pinned:
                    contradictions.append(
                        f"{rel(repo_root, skill_dir)}/SKILL.md:{offset + lineno}: "
                        f"body says {found} but frontmatter pins {value}"
                    )

    violations = [
        f"compatibility shape '{shape}' on {len(names)} skill(s): "
        f"{', '.join(sorted(names))}"
        for shape, names in sorted(shapes.items())
    ][1:]  # one shape is the target; every additional shape is the finding
    return violations + contradictions


# ---------------------------------------------------------------------------
# PD-8 / MNT-6 — advisory
# ---------------------------------------------------------------------------

# Deliberately excludes "Troubleshooting". A troubleshooting section is
# error-recovery *after* something fails; a gotchas section is the up-front
# "this will bite you" list the audit asked for. Including it would credit 5
# more skills (25 lacking instead of 30) for a section that does a different
# job. databricks-ml-training is the model.
_GOTCHA_RE = re.compile(r"gotcha|pitfall|common trap", re.IGNORECASE)


def check_pd_8(repo_root: Path) -> list[str]:
    """A SKILL.md with no gotchas-style section. Advisory."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        text = read_text(skill_dir / "SKILL.md")
        if any(_GOTCHA_RE.search(h) for h in _HEADING_RE.findall(text)):
            continue
        violations.append(
            f"{rel(repo_root, skill_dir)}/SKILL.md: no gotchas/pitfalls section"
        )
    return violations


_RUN_INTENT_RE = re.compile(
    r"(python3?\s+\S*scripts/|(run|execute|invoke|read)\s+[^\n]{0,40}scripts/)",
    re.IGNORECASE,
)


def check_mnt_6(repo_root: Path) -> list[str]:
    """A bundled `scripts/` with no stated run-vs-read intent. Advisory."""
    violations: list[str] = []
    for skill_dir in iter_all_skill_dirs(repo_root):
        scripts = skill_dir / "scripts"
        if not scripts.is_dir():
            continue
        if _RUN_INTENT_RE.search(read_text(skill_dir / "SKILL.md")):
            continue
        violations.append(
            f"{rel(repo_root, skill_dir)}/SKILL.md: bundles scripts/ without "
            "stating whether to run or read them"
        )
    return violations


# ---------------------------------------------------------------------------
# Registry + CLI
# ---------------------------------------------------------------------------

MUST_FIX = "must-fix"
ADVISORY = "advisory"
BLOCKED = "blocked"
ROLLUP = "rollup"

# Order is the remediation order, not alphabetical.
FINDINGS: tuple[tuple[str, str, str, object], ...] = (
    ("PD-6", MUST_FIX, "reference files over 100 lines with no TOC", check_pd_6),
    ("PD-5", MUST_FIX, "reference-to-reference links", check_pd_5),
    ("PD-5b", MUST_FIX, "nested references/ subdirectory", check_pd_5b),
    ("SPEC-10a-cross", MUST_FIX, "cross-skill '../' links", check_spec_10a_cross),
    ("SPEC-10a-intra", MUST_FIX, "intra-skill '../' links", check_spec_10a_intra),
    ("SPEC-10a-prose", MUST_FIX, "'../' .md paths in prose", check_spec_10a_prose),
    ("SPEC-10b", MUST_FIX, "bare-basename references", check_spec_10b),
    ("NEW-A", MUST_FIX, "dangling relative .md links", check_new_a),
    ("NEW-C", MUST_FIX, "reference files at the skill root", check_new_c),
    ("PD-4a", MUST_FIX, "pointer to a nonexistent skill", check_pd_4a),
    ("PD-4b", BLOCKED, "core children missing from core routing", check_pd_4b),
    ("PD-4c", MUST_FIX, "orphan reference files", check_pd_4c),
    ("PD-1", MUST_FIX, "SKILL.md over 500 lines", check_pd_1),
    ("PD-2", MUST_FIX, "SKILL.md over 5,000 tokens", check_pd_2),
    ("PD-3", ROLLUP, "skills over either ceiling (PD-1 u PD-2)", check_pd_3),
    ("DESC-1", MUST_FIX, "descriptions without trigger conditions", check_desc_1),
    ("TOK-5", BLOCKED, "uncontained preview/beta markers (strict)", check_tok_5),
    ("COMPAT-1", BLOCKED, "compatibility pin shapes beyond one", check_compat_1),
    ("SPEC-10a-fence", ADVISORY, "in-fence '../' (exempt, context only)",
     check_spec_10a_fence),
    ("SPEC-10a-self-parent", ADVISORY, "self-parent '../SKILL.md' (exempt)",
     check_spec_10a_self_parent),
    ("NEW-B", ADVISORY, "dangling link with an unknowable target", check_new_b),
    ("PD-8", ADVISORY, "SKILL.md with no gotchas section", check_pd_8),
    ("MNT-6", ADVISORY, "bundled scripts/ with no stated intent", check_mnt_6),
)

_SKILL_PREFIX_RE = re.compile(r"^(?:skills|experimental)/([^/]+)/")


def _by_skill(violations: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for violation in violations:
        match = _SKILL_PREFIX_RE.match(violation)
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Count the remediation audit's findings across skills/ and "
            "experimental/. Exit 0 when every selected must-fix finding is at "
            "zero."
        )
    )
    parser.add_argument(
        "--only",
        metavar="ID[,ID...]",
        help=(
            "restrict to these finding IDs (comma-separated). Selecting a "
            "blocked, advisory, or rollup finding makes it gate the exit status."
        ),
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="list every violation and the per-skill breakdown, not just counts",
    )
    args = parser.parse_args()

    known = {finding[0] for finding in FINDINGS}
    selected = known
    if args.only:
        selected = {part.strip() for part in args.only.split(",") if part.strip()}
        unknown = sorted(selected - known)
        if unknown:
            print(
                f"ERROR: unknown finding ID(s): {', '.join(unknown)}. "
                f"Known: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            sys.exit(2)

    repo_root = Path(__file__).resolve().parent.parent
    explicit = bool(args.only)
    failed = False
    rows = []
    per_skill_total: dict[str, int] = {}

    for finding_id, severity, title, check in FINDINGS:
        if finding_id not in selected:
            continue
        violations = check(repo_root)
        rows.append((finding_id, severity, len(violations), title))
        if violations and (severity == MUST_FIX or explicit):
            failed = True
        if severity == MUST_FIX:
            for name, count in _by_skill(violations).items():
                per_skill_total[name] = per_skill_total.get(name, 0) + count
        if not args.details:
            continue
        if violations:
            print(f"\n== {finding_id} ({severity}) — {title}: {len(violations)}")
            for violation in violations:
                print(f"  {violation}")
            per_skill = _by_skill(violations)
            if per_skill:
                print("  per skill: " + ", ".join(
                    f"{name} {count}" for name, count in
                    sorted(per_skill.items(), key=lambda kv: (-kv[1], kv[0]))
                ))

    print(f"\n{'FINDING':<20} {'SEVERITY':<9} {'COUNT':>6}  TITLE")
    for finding_id, severity, count, title in rows:
        print(f"{finding_id:<20} {severity:<9} {count:>6}  {title}")

    # Heaviest skill first: the remediation plan sorts its work this way, so
    # the gate prints the same ordering it is planned against.
    if per_skill_total:
        print(f"\n{'SKILL':<40} {'MUST-FIX':>8}")
        for name, count in sorted(
            per_skill_total.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            print(f"{name:<40} {count:>8}")

    must_fix_total = sum(
        count for _, severity, count, _ in rows if severity == MUST_FIX
    )
    stable_tokens, all_in_tokens = resident_set(repo_root)
    print(
        f"\nmust-fix total: {must_fix_total}  "
        f"(rollup and advisory rows are not summed)"
    )
    print(f"resident set: {stable_tokens} tokens stable / {all_in_tokens} all-in")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()


# --- Generated-artifact guard -------------------------------------------------
# plugins/**, manifest.json, rules/, hooks/, */agents/openai.yaml and */assets/
# are generated from metaplugin/plugin.meta.json by scripts/skills.py generate.
# Hand edits get silently overwritten, and mirroring a skills/ change into all
# four platform trees inflates a diff ~5x. Prose guardrails did not hold this;
# backpressure does.

import re as _re
import subprocess as _sp

_GENERATED = (
    _re.compile(r"^plugins/"),
    _re.compile(r"^manifest\.json$"),
    _re.compile(r"^rules/"),
    _re.compile(r"^hooks/.*\.json$"),
    _re.compile(r"^(skills|experimental)/[^/]+/agents/"),
    _re.compile(r"^(skills|experimental)/[^/]+/assets/"),
)


def check_generated_artifacts(base: str = "upstream/main") -> int:
    """Fail if the working branch touches generated output. Returns violation count."""
    try:
        merge_base = _sp.run(
            ["git", "merge-base", "HEAD", base],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        changed = _sp.run(
            ["git", "diff", "--name-only", merge_base],
            capture_output=True, text=True, check=True,
        ).stdout.split()
    except (_sp.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"GEN-1: cannot diff against {base} to check generated artifacts: {exc}"
        ) from exc

    hits = [p for p in changed if any(rx.match(p) for rx in _GENERATED)]
    if hits:
        shown = "\n  ".join(hits[:15])
        more = f"\n  ... and {len(hits) - 15} more" if len(hits) > 15 else ""
        raise RuntimeError(
            f"GEN-1 (must-fix): {len(hits)} generated artifacts modified.\n"
            f"  {shown}{more}\n"
            f"  Source of truth is metaplugin/plugin.meta.json.\n"
            f"  Fix: git checkout {base} -- plugins/ && "
            f"python3 scripts/skills.py generate"
        )
    return 0
