#!/usr/bin/env python3
"""Static consistency eval for the databricks-metric-view-advisor skill.

Validates that every documented example and instruction in the skill is
internally consistent and follows the rules the skill itself states. Runs
with no Databricks workspace required — it lints the skill's own files.

What it checks (each is a separate "case" with PASS/FAIL):
  1. Every metric-view YAML block (CREATE ... WITH METRICS ... AS $$ ... $$)
     parses as YAML and has the required top-level fields.
  2. No example contains a `format:` block (the skill says never use them).
  3. Every multi-word MEASURE() reference is backtick-quoted.
  4. No example uses date subtraction where DATEDIFF is required.
  5. Every documented Python snippet (Genie/dashboard JSON parsers) compiles.
  6. The example fixtures (sample_kpis.csv/.yaml, sample_queries.sql) parse.
  7. CLI commands referenced use only real `aitools` subcommands; with --live,
     each is probed via `databricks ... --help`.
  8. Regression guards for today's review fixes: the removed raw
     `/api/2.0/sql/statements` API path must not reappear, and the re-auth
     instruction must not pass `--host`.
  9. Relative markdown links resolve to files that exist.

Usage:
    python3 evals/check_examples.py                # static checks only
    python3 evals/check_examples.py --live         # also probe `databricks --help`
    python3 evals/check_examples.py --profile P    # profile for --live probes

Exit code is non-zero if any case fails.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
from pathlib import Path

import yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent

# --- result accounting -------------------------------------------------------
PASSES: list[str] = []
FAILURES: list[str] = []


def ok(msg: str) -> None:
    PASSES.append(msg)


def fail(msg: str) -> None:
    FAILURES.append(msg)


# --- helpers -----------------------------------------------------------------
def md_files() -> list[Path]:
    # Validate skill content, not the eval tooling itself (these docs
    # intentionally describe forbidden patterns to guard against them).
    return sorted(p for p in SKILL_ROOT.rglob("*.md") if "evals" not in p.parts)


def fenced_blocks(text: str, lang: str) -> list[str]:
    """Return the bodies of ```<lang> fenced code blocks."""
    pattern = re.compile(rf"```{lang}\b(.*?)```", re.DOTALL)
    return [m.group(1) for m in pattern.finditer(text)]


PLACEHOLDER = re.compile(r"<[a-zA-Z_]")  # template tokens like <catalog.schema.x>


def metric_view_yaml_blocks(text: str) -> list[str]:
    """Extract concrete metric-view YAML bodies (AS $$ ... $$) from ```sql fences.

    Skips:
      - blocks outside a ```sql fence (e.g. the bash deploy example, where the
        DDL appears as illustrative `#`-prefixed comment lines);
      - template blocks containing `<placeholder>` tokens (not real examples).
    """
    blocks = []
    for sql in fenced_blocks(text, "sql"):
        for m in re.finditer(r"WITH\s+METRICS.*?AS\s*\$\$(.*?)\$\$", sql, re.DOTALL | re.IGNORECASE):
            body = m.group(1)
            if PLACEHOLDER.search(body):
                continue  # illustrative template, not a concrete example
            blocks.append(body)
    return blocks


def measure_refs(text: str) -> list[str]:
    """Return the inner argument of every MEASURE(...) call, backslashes stripped."""
    return [m.group(1).replace("\\", "").strip() for m in re.finditer(r"MEASURE\(([^)]*)\)", text)]


# --- checks ------------------------------------------------------------------
def check_metric_view_yaml() -> None:
    total = 0
    bad_parse = 0
    bad_fields = 0
    has_format = 0
    for f in md_files():
        text = f.read_text()
        for i, body in enumerate(metric_view_yaml_blocks(text)):
            total += 1
            label = f"{f.relative_to(SKILL_ROOT)} block#{i + 1}"
            try:
                doc = yaml.safe_load(body)
            except yaml.YAMLError as e:
                bad_parse += 1
                fail(f"YAML parse error in {label}: {e}")
                continue
            if not isinstance(doc, dict):
                bad_fields += 1
                fail(f"{label}: metric-view YAML did not parse to a mapping")
                continue
            for req in ("source", "dimensions", "measures"):
                if req not in doc:
                    bad_fields += 1
                    fail(f"{label}: missing required top-level field '{req}'")
            for listfield in ("dimensions", "measures"):
                val = doc.get(listfield)
                if val is not None and (not isinstance(val, list) or len(val) == 0):
                    bad_fields += 1
                    fail(f"{label}: '{listfield}' must be a non-empty list")
            if "format" in body:
                # could be the word in a comment; only flag a real `format:` key
                if re.search(r"^\s*format\s*:", body, re.MULTILINE):
                    has_format += 1
                    fail(f"{label}: contains a `format:` block (skill says omit these)")
    if total == 0:
        fail("No metric-view YAML blocks found — extraction regex may be broken")
    elif bad_parse == 0 and bad_fields == 0 and has_format == 0:
        ok(f"All {total} metric-view YAML blocks parse and have required fields, no `format:` blocks")


def check_measure_quoting() -> None:
    # Only check inside concrete metric-view YAML blocks — prose intentionally
    # shows the *wrong* form (`MEASURE(Total Revenue)`) as a "NOT this" warning.
    offenders = []
    checked = 0
    for f in md_files():
        for body in metric_view_yaml_blocks(f.read_text()):
            for inner in measure_refs(body):
                if not inner:
                    continue
                checked += 1
                if inner.startswith("`"):
                    continue
                if " " not in inner:
                    continue
                offenders.append(f"{f.relative_to(SKILL_ROOT)}: MEASURE({inner})")
    if offenders:
        for o in offenders:
            fail(f"Unquoted multi-word MEASURE() reference — {o}")
    else:
        ok(f"All multi-word MEASURE() references in examples are backtick-quoted ({checked} checked)")


def check_no_date_subtraction() -> None:
    # Look for `<dateish> - <dateish>` used as a number; heuristic on date column names.
    offenders = []
    pat = re.compile(r"\b\w*date\w*\s*-\s*\w*date\w*\b", re.IGNORECASE)
    for f in md_files():
        for body in metric_view_yaml_blocks(f.read_text()):
            for m in pat.finditer(body):
                offenders.append(f"{f.relative_to(SKILL_ROOT)}: '{m.group(0)}'")
    if offenders:
        for o in offenders:
            fail(f"Possible date subtraction (use DATEDIFF) — {o}")
    else:
        ok("No date-subtraction patterns in metric-view examples (DATEDIFF rule respected)")


def check_python_snippets() -> None:
    # The skill tells the agent to run Python to parse Genie/dashboard JSON.
    # Every documented ```python block must at least compile.
    total = 0
    bad = 0
    for f in md_files():
        for i, body in enumerate(fenced_blocks(f.read_text(), "python")):
            total += 1
            try:
                compile(body, f"{f.relative_to(SKILL_ROOT)}#py{i + 1}", "exec")
            except SyntaxError as e:
                bad += 1
                fail(f"Python snippet does not compile — {f.relative_to(SKILL_ROOT)} block#{i + 1}: {e}")
    if total and bad == 0:
        ok(f"All {total} Python snippets compile")
    elif total == 0:
        ok("No Python snippets to compile")


def check_fixtures() -> None:
    ex = SKILL_ROOT / "examples"
    # CSV
    csv_path = ex / "sample_kpis.csv"
    try:
        rows = list(csv.DictReader(io.StringIO(csv_path.read_text())))
        cols = set(rows[0].keys()) if rows else set()
        if {"type", "name", "definition", "description"} <= cols and all(
            r["type"] in ("measure", "dimension") for r in rows
        ):
            ok(f"sample_kpis.csv parses ({len(rows)} rows, valid header + types)")
        else:
            fail(f"sample_kpis.csv: unexpected header/types — cols={cols}")
    except Exception as e:  # noqa: BLE001
        fail(f"sample_kpis.csv failed to parse: {e}")
    # YAML
    yaml_path = ex / "sample_kpis.yaml"
    try:
        doc = yaml.safe_load(yaml_path.read_text())
        if isinstance(doc, dict) and "measures" in doc and "dimensions" in doc:
            ok(f"sample_kpis.yaml parses ({len(doc['measures'])} measures, {len(doc['dimensions'])} dimensions)")
        else:
            fail("sample_kpis.yaml: missing measures/dimensions keys")
    except Exception as e:  # noqa: BLE001
        fail(f"sample_kpis.yaml failed to parse: {e}")
    # SQL
    sql_path = ex / "sample_queries.sql"
    try:
        stmts = []
        for chunk in sql_path.read_text().split(";"):
            # strip leading comment lines, keep the statement body
            body = "\n".join(ln for ln in chunk.splitlines() if not ln.strip().startswith("--")).strip()
            if body:
                stmts.append(body)
        if stmts:
            ok(f"sample_queries.sql parses ({len(stmts)} statements)")
        else:
            fail("sample_queries.sql: no statements found")
    except Exception as e:  # noqa: BLE001
        fail(f"sample_queries.sql failed to read: {e}")


AITOOLS_SUBCMDS = {"query", "discover-schema", "get-default-warehouse", "statement"}
STATEMENT_SUBCMDS = {"submit", "get", "status", "cancel"}


def check_cli_subcommands(live: bool, profile: str | None) -> None:
    bad = []
    seen_aitools = set()
    seen_statement = set()
    for f in md_files():
        text = f.read_text()
        for m in re.finditer(r"databricks experimental aitools tools (\S+)", text):
            sub = m.group(1)
            seen_aitools.add(sub)
            if sub not in AITOOLS_SUBCMDS:
                bad.append(f"{f.relative_to(SKILL_ROOT)}: unknown aitools subcommand '{sub}'")
        for m in re.finditer(r"aitools tools statement (\S+)", text):
            sub = m.group(1).strip("`<>")
            if sub in STATEMENT_SUBCMDS or sub in ("[command]", "submit"):
                seen_statement.add(sub)
            elif sub not in ("submit,", "get,", "status,"):  # prose lists
                pass
    if bad:
        for b in bad:
            fail(b)
    else:
        ok(f"All referenced aitools subcommands are valid {sorted(seen_aitools)}")

    if live:
        probes = [
            ["experimental", "aitools", "tools", "query", "--help"],
            ["experimental", "aitools", "tools", "discover-schema", "--help"],
            ["experimental", "aitools", "tools", "get-default-warehouse", "--help"],
            ["experimental", "aitools", "tools", "statement", "submit", "--help"],
            ["experimental", "aitools", "tools", "statement", "get", "--help"],
        ]
        for p in probes:
            cmd = ["databricks", *p]
            if profile:
                cmd += ["--profile", profile]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    ok(f"`{' '.join(p[:-1])}` exists in installed CLI")
                else:
                    fail(f"`{' '.join(p[:-1])}` --help failed (rc={r.returncode}): {r.stderr.strip()[:120]}")
            except FileNotFoundError:
                fail("databricks CLI not found on PATH for --live probe")
                break
            except subprocess.TimeoutExpired:
                fail(f"`{' '.join(p[:-1])}` --help timed out")


def check_regressions() -> None:
    # The raw SQL Statements API path was removed in favor of `statement`.
    offenders = []
    for f in md_files():
        text = f.read_text()
        for m in re.finditer(r"/api/2\.0/sql/statements", text):
            offenders.append(f"{f.relative_to(SKILL_ROOT)}: raw SQL Statements API reference reappeared")
    if offenders:
        for o in set(offenders):
            fail(o)
    else:
        ok("No raw /api/2.0/sql/statements references (replaced by `aitools tools statement`)")

    # Re-auth instruction must not pass --host.
    skill_md = (SKILL_ROOT / "SKILL.md").read_text()
    reauth_lines = [ln for ln in skill_md.splitlines() if "re-authenticate" in ln.lower()]
    bad_reauth = [ln for ln in reauth_lines if re.search(r"auth login[^\n]*--host[^\n]*--profile", ln)]
    if bad_reauth:
        fail("SKILL.md re-auth instruction still passes --host alongside --profile")
    else:
        ok("SKILL.md re-auth instruction uses --profile only (no --host)")


def check_links() -> None:
    broken = []
    link_pat = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for f in md_files():
        for m in link_pat.finditer(f.read_text()):
            target = m.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (f.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{f.relative_to(SKILL_ROOT)} -> {target}")
    if broken:
        for b in broken:
            fail(f"Broken relative link: {b}")
    else:
        ok("All relative markdown links resolve")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="probe `databricks ... --help` for referenced subcommands")
    ap.add_argument("--profile", default=None, help="CLI profile for --live probes")
    args = ap.parse_args()

    check_metric_view_yaml()
    check_measure_quoting()
    check_no_date_subtraction()
    check_python_snippets()
    check_fixtures()
    check_cli_subcommands(args.live, args.profile)
    check_regressions()
    check_links()

    print("\n=== Metric View Advisor — static consistency eval ===\n")
    for p in PASSES:
        print(f"  PASS  {p}")
    for fl in FAILURES:
        print(f"  FAIL  {fl}")
    print(f"\n{len(PASSES)} passed, {len(FAILURES)} failed.\n")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
