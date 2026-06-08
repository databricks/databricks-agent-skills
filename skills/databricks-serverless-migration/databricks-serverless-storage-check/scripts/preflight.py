#!/usr/bin/env python3
"""Serverless storage preflight: detect cross-task local-disk handoffs.

Scans Databricks notebooks, directories, DAB job YAML, or remote jobs/runs
for the antipattern where one task writes to /local_disk0, /tmp, or a
trustedTemp directory and another task reads from it. On serverless
compute, tasks may run on different nodes, so these handoffs fail with
`INTERNAL_ERROR: [Errno 13] Permission denied`.

Stdlib only. Optional `databricks` CLI for --job-id / --run-id modes.

Usage:
    preflight.py --notebook PATH [--json]
    preflight.py --dir PATH [--json]
    preflight.py --job-yaml PATH [--json]
    preflight.py --job-id ID --profile NAME [--json]
    preflight.py --run-id ID --profile NAME [--json]

Exit codes:
    0  clean (or info-only findings)
    1  warnings found
    2  blockers found
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Iterator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Local-disk path roots that are unsafe for cross-task sharing on serverless.
LOCAL_DISK_PREFIXES = (
    "/local_disk0",
    "/tmp",
    "/dbfs/tmp",
    "dbfs:/tmp",
)

# Exact BSI signature: /local_disk0/spark-<id>/trustedTemp-<id>/...
BSI_TRUSTED_TEMP_RE = re.compile(
    r"/local_disk0/spark-[A-Za-z0-9\-]+/trustedTemp[A-Za-z0-9\-]*"
)

# Generic trustedTemp anywhere in the path.
TRUSTED_TEMP_RE = re.compile(r"trustedTemp[A-Za-z0-9\-]*")

# Durable, cross-node storage roots. Paths starting with these are safe.
SAFE_PREFIXES = ("/Volumes/", "/Workspace/")

# Calls that move data to a child task / sibling. If a local-disk path
# flows into one of these, that's a cross-task handoff.
CHILD_CALL_NAMES = {
    "dbutils.notebook.run",
    "dbutils.jobs.taskValues.set",
    "dbutils.task_values.set",
}

# Calls that pull from a parent task. If the value is then used as a path
# starting with /local_disk0 or /tmp, the parent must have written it there.
PARENT_PULL_NAMES = {
    "dbutils.widgets.get",
    "dbutils.jobs.taskValues.get",
    "dbutils.task_values.get",
}

# Env-sync error signature (run-id mode only).
ENV_SYNC_RE = re.compile(
    r"ENVIRONMENT_SETUP_ERROR\.PYTHON_NOTEBOOK_ENVIRONMENT"
)

# Databricks notebook cell delimiter for .py source format.
PY_CELL_DELIM_RE = re.compile(r"^# COMMAND -+\s*$", re.MULTILINE)
PY_MAGIC_RE = re.compile(r"^# MAGIC %(\w+)\s*(.*)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------

SEVERITY_BLOCKER = "blocker"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITY_ORDER = {
    SEVERITY_BLOCKER: 2,
    SEVERITY_WARNING: 1,
    SEVERITY_INFO: 0,
}


@dataclass
class Finding:
    pattern_id: str
    severity: str
    file: str
    line: int
    snippet: str
    message: str
    fix: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Path classification helpers
# ---------------------------------------------------------------------------


def is_local_disk_path(value: str) -> bool:
    """True if the string looks like a local-disk path on Databricks compute."""
    if not isinstance(value, str) or not value:
        return False
    if TRUSTED_TEMP_RE.search(value):
        return True
    for prefix in LOCAL_DISK_PREFIXES:
        if value == prefix or value.startswith(prefix + "/"):
            return True
    return False


def is_bsi_signature(value: str) -> bool:
    """True if the string matches the exact BSI trustedTemp signature."""
    return bool(isinstance(value, str) and BSI_TRUSTED_TEMP_RE.search(value))


def is_safe_path(value: str) -> bool:
    """True if the string is a durable, cross-node storage path."""
    return isinstance(value, str) and any(
        value.startswith(p) for p in SAFE_PREFIXES
    )


# ---------------------------------------------------------------------------
# Notebook source extraction
# ---------------------------------------------------------------------------


@dataclass
class PythonCell:
    """A Python code block extracted from a notebook, with its source offset."""

    code: str
    start_line: int  # 1-indexed line in the original file


def extract_python_cells(file_path: Path) -> list[PythonCell]:
    """Return Python code cells from a .py or .ipynb notebook.

    For .py (Databricks source format), splits on `# COMMAND -----` and
    keeps only cells that are Python (no leading `# MAGIC %sql/%scala/%r`).
    For .ipynb, returns cells with `cell_type == "code"`. Magic-only cells
    (those that start with `%sql`, `%pip`, etc.) are skipped from AST
    analysis but remain visible to regex scans elsewhere.
    """
    suffix = file_path.suffix.lower()
    text = file_path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".ipynb":
        return _extract_ipynb_cells(text)
    return _extract_py_cells(text)


def _extract_py_cells(text: str) -> list[PythonCell]:
    cells: list[PythonCell] = []
    pos = 0
    line = 1
    parts = PY_CELL_DELIM_RE.split(text)
    for part in parts:
        stripped = part.lstrip("\n")
        leading = len(part) - len(stripped)
        # Skip cells whose first non-blank line is a magic that isn't %python.
        first_nonblank = next(
            (ln for ln in stripped.splitlines() if ln.strip()),
            "",
        )
        magic = PY_MAGIC_RE.match(first_nonblank)
        if magic and magic.group(1) not in ("python", "py"):
            line += part.count("\n")
            continue
        # Strip Databricks `# MAGIC ` prefixes from any python magic lines
        # so the remainder is valid Python for ast.parse.
        cleaned = "\n".join(
            re.sub(r"^# MAGIC ?", "", ln) for ln in stripped.splitlines()
        )
        if cleaned.strip():
            cells.append(PythonCell(code=cleaned, start_line=line + leading))
        line += part.count("\n")
    return cells


def _extract_ipynb_cells(text: str) -> list[PythonCell]:
    try:
        nb = json.loads(text)
    except json.JSONDecodeError:
        return []
    cells: list[PythonCell] = []
    synthetic_line = 1
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            synthetic_line += 1
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        first_nonblank = next(
            (ln for ln in source.splitlines() if ln.strip()),
            "",
        )
        if first_nonblank.startswith("%") and not first_nonblank.startswith(
            "%python"
        ):
            synthetic_line += source.count("\n") + 1
            continue
        cleaned = "\n".join(
            ln[len("%python") :] if ln.startswith("%python") else ln
            for ln in source.splitlines()
        )
        if cleaned.strip():
            cells.append(PythonCell(code=cleaned, start_line=synthetic_line))
        synthetic_line += source.count("\n") + 1
    return cells


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------


def _attr_chain(node: ast.AST) -> str | None:
    """Return a dotted name for an ast.Attribute chain like a.b.c, else None."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _call_qualname(node: ast.Call) -> str | None:
    """Return a dotted callable name like `dbutils.notebook.run`, else None."""
    return _attr_chain(node.func) if isinstance(node.func, ast.Attribute) else (
        node.func.id if isinstance(node.func, ast.Name) else None
    )


def _resolve_string(
    node: ast.AST, var_map: dict[str, str]
) -> str | None:
    """Return a string value for a constant or a Name bound to a constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in var_map:
        return var_map[node.id]
    return None


def _string_args(
    node: ast.Call, var_map: dict[str, str] | None = None
) -> list[tuple[str, int]]:
    """Yield (value, line) for every string positional/keyword arg.

    Resolves Name nodes against `var_map` (assignments earlier in the cell)
    and recurses into dict/list/tuple/set literals so paths passed via
    `{"k": tmp}` or `[tmp]` are still detected.
    """
    vm = var_map or {}
    out: list[tuple[str, int]] = []

    def _collect(value_node: ast.AST, lineno: int) -> None:
        s = _resolve_string(value_node, vm)
        if s is not None:
            out.append((s, lineno))
            return
        if isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
            for elt in value_node.elts:
                _collect(elt, getattr(elt, "lineno", lineno))
        elif isinstance(value_node, ast.Dict):
            for k, v in zip(value_node.keys, value_node.values):
                if k is not None:
                    _collect(k, getattr(k, "lineno", lineno))
                if v is not None:
                    _collect(v, getattr(v, "lineno", lineno))

    for arg in node.args:
        _collect(arg, arg.lineno)
    for kw in node.keywords:
        if kw.value is not None:
            _collect(kw.value, kw.value.lineno)
    return out


def _build_var_map(tree: ast.AST) -> dict[str, str]:
    """Build name -> string-literal map from top-level and nested Assigns."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (
            isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        ):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = node.value.value
    return out


def _all_string_constants(tree: ast.AST) -> Iterator[tuple[str, int]]:
    """Yield (value, lineno) for every string Constant anywhere in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, node.lineno


class _NotebookScanner(ast.NodeVisitor):
    """Collects local-disk writes, child calls, and parent pulls in a cell."""

    def __init__(self, cell: PythonCell, file_path: str):
        self.cell = cell
        self.file = file_path
        self.var_map: dict[str, str] = {}
        self.local_writes: list[tuple[str, int, str]] = []  # (path, line, snippet)
        self.child_calls: list[tuple[str, int, str, str]] = []  # (path, line, snippet, callname)
        self.parent_reads: list[tuple[str, int, str]] = []  # (path, line, snippet)
        self.fs_cp_local_to_local: list[tuple[str, str, int, str]] = []
        self.bsi_hits: list[tuple[str, int, str]] = []
        self.all_local_paths: set[str] = set()

    # ---- entrypoint ----
    def scan(self) -> None:
        try:
            tree = ast.parse(self.cell.code)
        except SyntaxError:
            return
        self.var_map = _build_var_map(tree)
        # Walk every string constant in the cell once. This catches BSI
        # signatures bound to variables (e.g. `tmp = "/local_disk0/.../trustedTemp/..."`)
        # and seeds the "this cell touches these local paths" set used by
        # the DAB sibling-sharing analysis.
        for value, lineno in _all_string_constants(tree):
            if is_local_disk_path(value):
                self.all_local_paths.add(value)
            if is_bsi_signature(value):
                self.bsi_hits.append(
                    (value, self._real_line(lineno), self._snippet(lineno))
                )
        # Also include resolved variable values in case the constant is
        # only an attribute of a longer chain we missed.
        for value in self.var_map.values():
            if is_local_disk_path(value):
                self.all_local_paths.add(value)
        self.visit(tree)

    # ---- helpers ----
    def _real_line(self, lineno: int) -> int:
        return self.cell.start_line + lineno - 1

    def _snippet(self, lineno: int) -> str:
        lines = self.cell.code.splitlines()
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()
        return ""

    # ---- visitors ----
    def visit_Call(self, node: ast.Call) -> None:
        callname = _call_qualname(node)
        strings = _string_args(node, self.var_map)

        # Child calls (parent writes flowing out)
        if callname in CHILD_CALL_NAMES:
            for s, ln in strings:
                if is_local_disk_path(s):
                    self.child_calls.append(
                        (s, self._real_line(ln), self._snippet(ln), callname)
                    )

        # File writes to local-disk paths (open(..., "w"), pandas to_*, spark.write.*)
        write_path = _detect_write_target(node, callname, self.var_map)
        if write_path is not None:
            value, lineno = write_path
            if is_local_disk_path(value):
                self.local_writes.append(
                    (value, self._real_line(lineno), self._snippet(lineno))
                )
                self.all_local_paths.add(value)

        # dbutils.fs.cp local-to-local (heuristic)
        if callname in ("dbutils.fs.cp", "dbutils.fs.mv"):
            cp_strings = [s for s, _ in strings if isinstance(s, str)]
            if (
                len(cp_strings) >= 2
                and is_local_disk_path(cp_strings[0])
                and is_local_disk_path(cp_strings[1])
            ):
                ln = strings[0][1]
                self.fs_cp_local_to_local.append(
                    (
                        cp_strings[0],
                        cp_strings[1],
                        self._real_line(ln),
                        self._snippet(ln),
                    )
                )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect: x = dbutils.widgets.get("path"); open(x); etc.
        # We approximate: if RHS is a parent-pull call and the variable is
        # later used as a path argument to open() or a read_* call, that
        # would be FANOUT002. Without dataflow, we surface a softer signal:
        # if RHS is a parent-pull AND any local-disk string literal exists
        # in the same cell as a read target, we'll catch it via direct
        # string-literal reads below.
        self.generic_visit(node)


def _detect_write_target(
    node: ast.Call, callname: str | None, var_map: dict[str, str]
) -> tuple[str, int] | None:
    """Return (path_string, lineno) if the call writes to a path, else None.

    Resolves Name args via `var_map` so writes through a local variable
    (e.g. `tmp = "/local_disk0/..."; pd.DataFrame(...).to_parquet(tmp)`)
    are still detected.
    """
    if callname is None:
        return None

    def _resolve(arg: ast.AST) -> str | None:
        return _resolve_string(arg, var_map)

    # open(path, "w"|"wb"|"a"|...)
    if callname == "open" and node.args:
        mode = None
        for arg in node.args[1:]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                mode = arg.value
                break
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    mode = kw.value.value
        if mode and any(c in mode for c in ("w", "a", "x")):
            s = _resolve(node.args[0])
            if s is not None:
                return s, node.args[0].lineno

    # spark.write.* / DataFrame.write.* (heuristic: any call whose name
    # ends in .save / .saveAsTable / .parquet / .csv / .json / .text / .orc /
    # .delta / .insertInto with a string arg)
    write_terminals = {
        "save",
        "saveAsTable",
        "parquet",
        "csv",
        "json",
        "text",
        "orc",
    }
    last = callname.split(".")[-1]
    if last in write_terminals and node.args:
        s = _resolve(node.args[0])
        if s is not None:
            return s, node.args[0].lineno

    # pandas: df.to_csv, df.to_parquet, df.to_json, df.to_pickle
    if last.startswith("to_") and node.args:
        s = _resolve(node.args[0])
        if s is not None:
            return s, node.args[0].lineno

    # shutil.copy / copyfile / move (dest is arg 1)
    if callname in ("shutil.copy", "shutil.copyfile", "shutil.move") and len(node.args) >= 2:
        s = _resolve(node.args[1])
        if s is not None:
            return s, node.args[1].lineno

    # dbutils.fs.put(path, contents, overwrite?)
    if callname == "dbutils.fs.put" and node.args:
        s = _resolve(node.args[0])
        if s is not None:
            return s, node.args[0].lineno

    return None


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------


def _read_targets_in_cell(scanner: _NotebookScanner) -> list[tuple[str, int, str]]:
    """Best-effort detection of reads from local-disk string literals.

    Catches open(path, "r"), pd.read_*, spark.read.* with string args.
    Resolves Name args via the scanner's var_map.
    """
    out: list[tuple[str, int, str]] = []
    try:
        tree = ast.parse(scanner.cell.code)
    except SyntaxError:
        return out

    read_terminals = {
        "parquet",
        "csv",
        "json",
        "text",
        "orc",
        "table",
        "load",
    }
    vm = scanner.var_map

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callname = _call_qualname(node)
        strings = _string_args(node, vm)
        if callname == "open":
            mode = "r"
            for arg in node.args[1:]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    mode = arg.value
                    break
            if "r" in mode and not any(c in mode for c in ("w", "a", "x")):
                for s, ln in strings[:1]:
                    if is_local_disk_path(s):
                        out.append((s, scanner._real_line(ln), scanner._snippet(ln)))
                        scanner.all_local_paths.add(s)
        elif callname and callname.split(".")[-1] in read_terminals:
            for s, ln in strings[:1]:
                if is_local_disk_path(s):
                    out.append((s, scanner._real_line(ln), scanner._snippet(ln)))
                    scanner.all_local_paths.add(s)
        elif callname and callname.split(".")[-1].startswith("read_"):
            for s, ln in strings[:1]:
                if is_local_disk_path(s):
                    out.append((s, scanner._real_line(ln), scanner._snippet(ln)))
                    scanner.all_local_paths.add(s)
    return out


def scan_notebook(file_path: Path) -> list[Finding]:
    """Scan a single notebook and emit FANOUT findings."""
    findings: list[Finding] = []
    rel = str(file_path)
    cells = extract_python_cells(file_path)

    has_child_call_anywhere = False
    has_local_write_anywhere = False
    has_local_read_anywhere = False

    cell_scanners: list[_NotebookScanner] = []
    for cell in cells:
        scanner = _NotebookScanner(cell, rel)
        scanner.scan()
        cell_scanners.append(scanner)
        if scanner.child_calls:
            has_child_call_anywhere = True
        if scanner.local_writes:
            has_local_write_anywhere = True

    for scanner in cell_scanners:
        # FANOUT006 — BSI signature (always blocker, regardless of context)
        for path, line, snippet in scanner.bsi_hits:
            findings.append(
                Finding(
                    pattern_id="FANOUT006",
                    severity=SEVERITY_BLOCKER,
                    file=rel,
                    line=line,
                    snippet=snippet,
                    message=(
                        f"Hardcoded path matches the exact BSI trustedTemp "
                        f"signature: {path!r}. This is a known-bad cross-node "
                        f"path on serverless."
                    ),
                    fix=(
                        "Replace with /Volumes/<catalog>/<schema>/<volume>/"
                        "handoff/<run_id>/... or /Workspace/Shared/<job>/...; "
                        "see references/remediation-guide.md."
                    ),
                )
            )

        # FANOUT001 — local-disk path passed to a child call
        for path, line, snippet, callname in scanner.child_calls:
            findings.append(
                Finding(
                    pattern_id="FANOUT001",
                    severity=SEVERITY_BLOCKER,
                    file=rel,
                    line=line,
                    snippet=snippet,
                    message=(
                        f"Local-disk path {path!r} passed to {callname}. "
                        f"Child tasks may run on a different node and will "
                        f"hit Permission denied."
                    ),
                    fix=(
                        "Write the handoff to /Volumes/<catalog>/<schema>/"
                        "<volume>/... or /Workspace/Shared/... and pass that "
                        "path instead. For small payloads, use "
                        "dbutils.jobs.taskValues with no file."
                    ),
                )
            )

        # FANOUT002 — local-disk read in a notebook that is also called by a parent
        # We can't see the caller statically, so we surface reads of /local_disk0
        # or /tmp as warnings when they appear in a notebook that ALSO contains
        # widgets/taskValues.get (suggesting it's a child notebook).
        is_likely_child = any(
            re.search(r"dbutils\.(widgets|jobs\.taskValues|task_values)\.get",
                      c.code)
            for c in cells
        )
        for path, line, snippet in _read_targets_in_cell(scanner):
            if is_likely_child:
                findings.append(
                    Finding(
                        pattern_id="FANOUT002",
                        severity=SEVERITY_BLOCKER,
                        file=rel,
                        line=line,
                        snippet=snippet,
                        message=(
                            f"Child notebook reads from local-disk path "
                            f"{path!r}. On serverless, the parent task that "
                            f"wrote this file may have run on a different node."
                        ),
                        fix=(
                            "Have the parent write to /Volumes/... or "
                            "/Workspace/... and read from there. For scalars "
                            "and small JSON, use dbutils.jobs.taskValues."
                        ),
                    )
                )

        # FANOUT005 — dbutils.fs.cp local→local in a multi-task context (heuristic)
        for src, dst, line, snippet in scanner.fs_cp_local_to_local:
            findings.append(
                Finding(
                    pattern_id="FANOUT005",
                    severity=SEVERITY_INFO,
                    file=rel,
                    line=line,
                    snippet=snippet,
                    message=(
                        f"dbutils.fs.cp from {src!r} to {dst!r} — both on local "
                        f"disk. Safe within a single task only."
                    ),
                    fix=(
                        "If this notebook is invoked by a multi-task job, use "
                        "/Volumes/... or /Workspace/... for cross-task data."
                    ),
                )
            )

    return findings


def scan_path(target: Path) -> list[Finding]:
    """Scan a single notebook or a directory of notebooks."""
    findings: list[Finding] = []
    if target.is_file():
        if target.suffix.lower() in (".py", ".ipynb"):
            findings.extend(scan_notebook(target))
        return findings
    if target.is_dir():
        for path in sorted(target.rglob("*")):
            if path.suffix.lower() in (".py", ".ipynb"):
                findings.extend(scan_notebook(path))
    return findings


# ---------------------------------------------------------------------------
# DAB YAML analysis
# ---------------------------------------------------------------------------


def _try_load_yaml(text: str) -> dict | None:
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    try:
        return yaml.safe_load(text)
    except Exception:
        return None


def _leading_spaces(line: str) -> int:
    """Count leading spaces. Treats a tab as 4 spaces (good enough for DABs)."""
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4
        else:
            break
    return n


def _minimal_yaml_tasks(text: str) -> list[dict]:
    """Stdlib-only fallback: extract a flat task list from a DAB YAML.

    Indent-aware. The top-level task indent is the column of the first
    `- task_key:` line under `tasks:`. Any subsequent `- task_key:` line
    at a DEEPER indent is treated as a depends_on entry, not a new task.
    """
    tasks: list[dict] = []
    in_tasks = False
    tasks_indent: int | None = None  # indent of `tasks:` keyword
    task_item_indent: int | None = None  # indent of `- task_key:` lines
    cur: dict | None = None
    in_depends = False
    depends_indent: int | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        indent = _leading_spaces(line)

        # `tasks:` declaration
        if re.match(r"^\s*tasks\s*:\s*$", line):
            in_tasks = True
            tasks_indent = indent
            task_item_indent = None
            cur = None
            continue

        if not in_tasks:
            continue

        # Left the tasks: block (we hit something at <= tasks_indent that
        # isn't a child of tasks:).
        if tasks_indent is not None and indent <= tasks_indent and not re.match(
            r"^\s*tasks\s*:\s*$", line
        ):
            if cur is not None:
                tasks.append(cur)
                cur = None
            in_tasks = False
            continue

        # New top-level task entry
        m = re.match(r"^(\s*)-\s*task_key\s*:\s*(\S+)\s*$", line)
        if m and (task_item_indent is None or indent == task_item_indent):
            if cur is not None:
                tasks.append(cur)
            task_item_indent = indent
            cur = {"task_key": m.group(2).strip("\"'"), "depends_on": []}
            in_depends = False
            continue

        if cur is None:
            continue

        # Enter / leave depends_on block
        if re.match(r"^\s*depends_on\s*:\s*$", line):
            in_depends = True
            depends_indent = indent
            continue
        if in_depends and depends_indent is not None and indent <= depends_indent:
            in_depends = False

        # depends_on entries: `- task_key: X` deeper than depends_indent
        if in_depends:
            m = re.match(r"^\s*-\s*task_key\s*:\s*(\S+)\s*$", line)
            if m:
                cur["depends_on"].append(m.group(1).strip("\"'"))
            continue

        # Task-level keys
        m = re.match(r"^\s*notebook_path\s*:\s*(\S+)\s*$", line)
        if m:
            cur["notebook_path"] = m.group(1).strip("\"'")
            continue
        m = re.match(r"^\s*pipeline_id\s*:\s*(\S+)\s*$", line)
        if m:
            cur["pipeline_id"] = m.group(1)
            continue
        if re.match(r"^\s*pipeline_task\s*:\s*$", line):
            cur["is_pipeline_task"] = True
            continue

    if cur is not None:
        tasks.append(cur)
    return tasks


def _tasks_from_loaded(doc: dict) -> list[dict]:
    """Extract task dicts from a loaded DAB YAML doc."""
    out: list[dict] = []
    if not isinstance(doc, dict):
        return out
    resources = doc.get("resources") or {}
    jobs = (resources.get("jobs") or {}) if isinstance(resources, dict) else {}
    if not isinstance(jobs, dict):
        return out
    for job_def in jobs.values():
        if not isinstance(job_def, dict):
            continue
        for task in job_def.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            entry = {
                "task_key": task.get("task_key"),
                "depends_on": [
                    d.get("task_key")
                    for d in (task.get("depends_on") or [])
                    if isinstance(d, dict)
                ],
            }
            notebook = task.get("notebook_task") or {}
            if isinstance(notebook, dict) and "notebook_path" in notebook:
                entry["notebook_path"] = notebook["notebook_path"]
            if "pipeline_task" in task:
                entry["is_pipeline_task"] = True
            out.append(entry)
    return out


def scan_job_yaml(yaml_path: Path) -> list[Finding]:
    """Scan a DAB job YAML for sibling-task local-disk sharing patterns."""
    findings: list[Finding] = []
    text = yaml_path.read_text(encoding="utf-8", errors="replace")

    doc = _try_load_yaml(text)
    tasks = _tasks_from_loaded(doc) if doc else _minimal_yaml_tasks(text)

    # Resolve referenced notebooks (relative to the YAML's parent dir or
    # to the bundle root, taking the simplest interpretation).
    base = yaml_path.parent
    bundle_root_candidates = [base, base.parent]
    referenced: list[Path] = []
    for task in tasks:
        nb = task.get("notebook_path")
        if not nb:
            continue
        # Strip the .py/.ipynb suffix if missing; try both.
        for root in bundle_root_candidates:
            for ext in ("", ".py", ".ipynb"):
                candidate = (root / (nb.lstrip("./") + ext)).resolve()
                if candidate.exists():
                    referenced.append(candidate)
                    break
            else:
                continue
            break

    # Scan referenced notebooks for any local-disk paths the notebook
    # touches (writes, reads, child-call args, or bare string literals).
    notebook_local_paths: dict[Path, set[str]] = {}
    for nb_path in referenced:
        paths: set[str] = set()
        for cell in extract_python_cells(nb_path):
            scanner = _NotebookScanner(cell, str(nb_path))
            scanner.scan()
            _read_targets_in_cell(scanner)  # populates scanner.all_local_paths
            paths.update(scanner.all_local_paths)
        notebook_local_paths[nb_path] = paths

        # Per-notebook findings still apply when scanning a job.
        findings.extend(scan_notebook(nb_path))

    # FANOUT003 — sibling tasks share a local-disk path
    path_to_tasks: dict[str, list[str]] = {}
    for task in tasks:
        nb = task.get("notebook_path")
        if not nb:
            continue
        for resolved, paths in notebook_local_paths.items():
            if nb.lstrip("./") in resolved.as_posix():
                for p in paths:
                    path_to_tasks.setdefault(p, []).append(task["task_key"])

    for path, keys in path_to_tasks.items():
        unique_keys = sorted(set(k for k in keys if k))
        if len(unique_keys) > 1:
            findings.append(
                Finding(
                    pattern_id="FANOUT003",
                    severity=SEVERITY_WARNING,
                    file=str(yaml_path),
                    line=0,
                    snippet=f"tasks: {', '.join(unique_keys)}",
                    message=(
                        f"Multiple sibling tasks reference local-disk path "
                        f"{path!r}. On serverless, these tasks may run on "
                        f"different nodes and cannot share local files."
                    ),
                    fix=(
                        "Move the shared artifact to /Volumes/... or "
                        "/Workspace/... and update both tasks to use that path."
                    ),
                )
            )

    # FANOUT004 — pipeline_task downstream of notebook_task that wrote local
    task_by_key = {t.get("task_key"): t for t in tasks if t.get("task_key")}
    notebook_wrote_local: set[str] = set()
    for task in tasks:
        key = task.get("task_key")
        nb = task.get("notebook_path")
        if not key or not nb:
            continue
        for resolved, paths in notebook_local_paths.items():
            if nb.lstrip("./") in resolved.as_posix() and paths:
                notebook_wrote_local.add(key)
                break
    for task in tasks:
        if not task.get("is_pipeline_task"):
            continue
        upstream = task.get("depends_on") or []
        if any(u in notebook_wrote_local for u in upstream):
            findings.append(
                Finding(
                    pattern_id="FANOUT004",
                    severity=SEVERITY_WARNING,
                    file=str(yaml_path),
                    line=0,
                    snippet=f"pipeline_task {task.get('task_key')} depends_on {upstream}",
                    message=(
                        f"pipeline_task {task.get('task_key')!r} depends on a "
                        f"notebook_task that wrote to local disk. The pipeline "
                        f"will not see those files."
                    ),
                    fix=(
                        "Have the upstream notebook write to /Volumes/... and "
                        "configure the pipeline to read from that location."
                    ),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Remote modes (--job-id, --run-id) — shell out to databricks CLI
# ---------------------------------------------------------------------------


def _databricks_cli(args: list[str], profile: str) -> str:
    """Run `databricks` CLI with the given profile, return stdout."""
    cmd = ["databricks"] + args + ["--profile", profile, "--output", "json"]
    result = subprocess.run(
        cmd, check=False, capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"databricks CLI failed: {' '.join(cmd)}\n{result.stderr}"
        )
    return result.stdout


def scan_remote_job(job_id: str, profile: str) -> list[Finding]:
    """Pull notebook source for every task in a remote job and scan."""
    raw = _databricks_cli(["jobs", "get", "--job-id", job_id], profile)
    job = json.loads(raw)
    tasks = (job.get("settings") or {}).get("tasks") or []

    tmp_dir = Path("/tmp") / f"preflight-job-{job_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    findings: list[Finding] = []
    notebook_paths: dict[str, Path] = {}
    for task in tasks:
        nb = (task.get("notebook_task") or {}).get("notebook_path")
        if not nb:
            continue
        local = tmp_dir / (task["task_key"] + ".py")
        try:
            _databricks_cli(
                [
                    "workspace",
                    "export",
                    nb,
                    "--format",
                    "SOURCE",
                    "--file",
                    str(local),
                ],
                profile,
            )
        except RuntimeError as exc:
            findings.append(
                Finding(
                    pattern_id="FANOUT000",
                    severity=SEVERITY_INFO,
                    file=nb,
                    line=0,
                    snippet="",
                    message=f"Could not export {nb}: {exc}",
                    fix="Verify the notebook path and your CLI permissions.",
                )
            )
            continue
        notebook_paths[task["task_key"]] = local
        findings.extend(scan_notebook(local))

    return findings


def scan_run_output(run_id: str, profile: str) -> list[Finding]:
    """Pull run output and classify the error trace as fan-out vs env-sync."""
    raw = _databricks_cli(["jobs", "get-run-output", "--run-id", run_id], profile)
    payload = json.loads(raw)
    error = (payload.get("error") or "") + "\n" + (payload.get("error_trace") or "")

    findings: list[Finding] = []
    if ENV_SYNC_RE.search(error):
        findings.append(
            Finding(
                pattern_id="ENV001",
                severity=SEVERITY_INFO,
                file=f"run/{run_id}",
                line=0,
                snippet="ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT",
                message=(
                    "The run failed with the rare, platform-side env-sync "
                    "error. This skill does not fix this — escalate to "
                    "Databricks engineering support."
                ),
                fix=(
                    "Open an ES ticket (use /jira-actions or /support-"
                    "escalation) with the run ID and full error trace. As a "
                    "mitigation, reduce dependency setup during child "
                    "notebook startup and add task retries."
                ),
            )
        )

    bsi_hits = BSI_TRUSTED_TEMP_RE.findall(error)
    for hit in bsi_hits:
        findings.append(
            Finding(
                pattern_id="FANOUT006",
                severity=SEVERITY_BLOCKER,
                file=f"run/{run_id}",
                line=0,
                snippet=hit,
                message=(
                    f"Run output contains the BSI trustedTemp signature "
                    f"{hit!r}. This is the cross-task local-disk antipattern."
                ),
                fix=(
                    "Locate the task that wrote to /local_disk0/spark-.../"
                    "trustedTemp-... and rewrite the handoff to use "
                    "/Volumes/... or /Workspace/..."
                ),
            )
        )

    # Generic permission-denied on local-disk path
    perm_re = re.compile(
        r"Permission denied:\s*['\"]?(/local_disk0[^'\"\s]*|/tmp/[^'\"\s]*)"
    )
    for m in perm_re.finditer(error):
        path = m.group(1)
        # Skip if already covered by FANOUT006 above.
        if BSI_TRUSTED_TEMP_RE.search(path):
            continue
        findings.append(
            Finding(
                pattern_id="FANOUT001",
                severity=SEVERITY_BLOCKER,
                file=f"run/{run_id}",
                line=0,
                snippet=f"Permission denied: {path}",
                message=(
                    f"Run failed with Permission denied on local-disk path "
                    f"{path!r}. Likely a cross-task handoff."
                ),
                fix=(
                    "Identify the writing task and move the handoff to "
                    "/Volumes/... or /Workspace/..."
                ),
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_human(findings: list[Finding]) -> str:
    if not findings:
        return "No serverless storage issues found.\n"

    by_sev: dict[str, list[Finding]] = {
        SEVERITY_BLOCKER: [],
        SEVERITY_WARNING: [],
        SEVERITY_INFO: [],
    }
    for f in findings:
        by_sev[f.severity].append(f)

    out: list[str] = []
    out.append(
        f"Serverless storage preflight: {len(findings)} finding(s) "
        f"({len(by_sev[SEVERITY_BLOCKER])} blocker, "
        f"{len(by_sev[SEVERITY_WARNING])} warning, "
        f"{len(by_sev[SEVERITY_INFO])} info)"
    )
    out.append("=" * 72)

    label = {
        SEVERITY_BLOCKER: "BLOCKER",
        SEVERITY_WARNING: "WARNING",
        SEVERITY_INFO: "INFO",
    }
    for sev in (SEVERITY_BLOCKER, SEVERITY_WARNING, SEVERITY_INFO):
        items = by_sev[sev]
        if not items:
            continue
        out.append("")
        out.append(f"[{label[sev]}] {len(items)} finding(s)")
        out.append("-" * 72)
        for f in items:
            location = (
                f"{f.file}:{f.line}" if f.line else f.file
            )
            out.append(f"  [{f.pattern_id}] {location}")
            if f.snippet:
                out.append(f"    > {f.snippet}")
            out.append(f"    {f.message}")
            out.append(f"    Fix: {f.fix}")
            out.append("")
    return "\n".join(out)


def format_json(findings: list[Finding]) -> str:
    payload = {
        "findings": [f.to_dict() for f in findings],
        "summary": {
            "blocker": sum(1 for f in findings if f.severity == SEVERITY_BLOCKER),
            "warning": sum(1 for f in findings if f.severity == SEVERITY_WARNING),
            "info": sum(1 for f in findings if f.severity == SEVERITY_INFO),
            "total": len(findings),
        },
    }
    return json.dumps(payload, indent=2)


def exit_code_for(findings: list[Finding]) -> int:
    if any(f.severity == SEVERITY_BLOCKER for f in findings):
        return 2
    if any(f.severity == SEVERITY_WARNING for f in findings):
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="preflight.py",
        description=(
            "Detect cross-task local-disk handoffs in Databricks serverless "
            "jobs and notebooks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--notebook", type=Path, help="Scan a single .py or .ipynb")
    mode.add_argument("--dir", type=Path, help="Recursively scan a directory")
    mode.add_argument("--job-yaml", type=Path, help="Scan a DAB job YAML")
    mode.add_argument("--job-id", type=str, help="Scan a remote job by ID")
    mode.add_argument("--run-id", type=str, help="Classify a failed run's error trace")
    p.add_argument(
        "--profile",
        type=str,
        default="DEFAULT",
        help="Databricks CLI profile (required for --job-id / --run-id)",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings: list[Finding] = []

    if args.notebook:
        findings = scan_path(args.notebook)
    elif args.dir:
        findings = scan_path(args.dir)
    elif args.job_yaml:
        findings = scan_job_yaml(args.job_yaml)
    elif args.job_id:
        findings = scan_remote_job(args.job_id, args.profile)
    elif args.run_id:
        findings = scan_run_output(args.run_id, args.profile)

    findings.sort(
        key=lambda f: (
            -SEVERITY_ORDER[f.severity],
            f.file,
            f.line,
            f.pattern_id,
        )
    )

    if args.json:
        print(format_json(findings))
    else:
        print(format_human(findings))

    return exit_code_for(findings)


if __name__ == "__main__":
    sys.exit(main())
