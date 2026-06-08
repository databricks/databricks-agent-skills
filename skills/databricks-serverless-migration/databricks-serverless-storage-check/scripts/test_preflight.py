#!/usr/bin/env python3
"""Self-test fixtures and assertions for preflight.py.

Run with:
    python3 scripts/test_preflight.py

Exits 0 if all assertions pass, 1 otherwise. Uses only the stdlib +
preflight.py itself; no test framework dependency.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import preflight  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

BSI_PARENT_NOTEBOOK = """\
# BSI-pattern parent: writes to trustedTemp and hands off via dbutils.notebook.run
import pandas as pd

tmp = "/local_disk0/spark-d6bae111-42bd-4f54/trustedTemp-55adadbe/handoff.parquet"
pd.DataFrame({"x": [1, 2, 3]}).to_parquet(tmp)

dbutils.notebook.run("./child", 600, {"handoff_path": tmp})
"""

BSI_CHILD_NOTEBOOK = """\
# BSI-pattern child: reads from a /local_disk0 path passed in as a widget
import pandas as pd

dbutils.widgets.text("handoff_path", "")
path = dbutils.widgets.get("handoff_path")
df = pd.read_parquet("/local_disk0/spark-d6bae111-42bd-4f54/trustedTemp-55adadbe/handoff.parquet")
print(df)
"""

CLEAN_VOLUMES_NOTEBOOK = """\
# Clean: uses /Volumes for cross-task handoff
import pandas as pd

handoff = "/Volumes/main/analytics/handoffs/run_42/data.parquet"
pd.DataFrame({"x": [1, 2, 3]}).to_parquet(handoff)

dbutils.notebook.run("./child", 600, {"handoff_path": handoff})
"""

DAB_YAML_SHARED_TMP = """\
resources:
  jobs:
    my_job:
      name: my_job
      tasks:
        - task_key: producer
          notebook_task:
            notebook_path: ./producer.py
        - task_key: consumer
          depends_on:
            - task_key: producer
          notebook_task:
            notebook_path: ./consumer.py
"""

PRODUCER_NOTEBOOK = """\
import pandas as pd
shared = "/tmp/foo.parquet"
pd.DataFrame({"x": [1]}).to_parquet(shared)
"""

CONSUMER_NOTEBOOK = """\
import pandas as pd
shared = "/tmp/foo.parquet"
df = pd.read_parquet(shared)
"""

ENV_SYNC_RUN_OUTPUT = json.dumps(
    {
        "error": "ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT",
        "error_trace": "Virtual environment changed while syncing",
    }
)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


class TestFailure(Exception):
    pass


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise TestFailure(msg)


def has_finding(findings, pattern_id: str) -> bool:
    return any(f.pattern_id == pattern_id for f in findings)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bsi_pattern_blockers():
    """BSI repro: parent + child notebooks together trigger 001, 002, 006."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "parent.py").write_text(BSI_PARENT_NOTEBOOK)
        (d / "child.py").write_text(BSI_CHILD_NOTEBOOK)

        findings = preflight.scan_path(d)
        expect(
            has_finding(findings, "FANOUT001"),
            f"expected FANOUT001 in BSI parent, got: {[f.pattern_id for f in findings]}",
        )
        expect(
            has_finding(findings, "FANOUT002"),
            f"expected FANOUT002 in BSI child, got: {[f.pattern_id for f in findings]}",
        )
        expect(
            has_finding(findings, "FANOUT006"),
            f"expected FANOUT006 for trustedTemp signature, got: "
            f"{[f.pattern_id for f in findings]}",
        )
        expect(
            preflight.exit_code_for(findings) == 2,
            f"expected exit code 2 for blockers, got {preflight.exit_code_for(findings)}",
        )


def test_clean_volumes_notebook():
    """Notebook using /Volumes produces zero findings, exit 0."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(CLEAN_VOLUMES_NOTEBOOK)
        path = Path(f.name)
    try:
        findings = preflight.scan_path(path)
        expect(
            findings == [],
            f"expected no findings, got: {[(f.pattern_id, f.snippet) for f in findings]}",
        )
        expect(
            preflight.exit_code_for(findings) == 0,
            "expected exit 0 on clean notebook",
        )
    finally:
        path.unlink()


def test_dab_yaml_shared_tmp():
    """DAB YAML with sibling tasks reading/writing /tmp triggers FANOUT003."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "producer.py").write_text(PRODUCER_NOTEBOOK)
        (d / "consumer.py").write_text(CONSUMER_NOTEBOOK)
        yaml = d / "my_job.job.yml"
        yaml.write_text(DAB_YAML_SHARED_TMP)

        findings = preflight.scan_job_yaml(yaml)
        expect(
            has_finding(findings, "FANOUT003"),
            f"expected FANOUT003 for sibling-shared /tmp, got: "
            f"{[f.pattern_id for f in findings]}",
        )
        # Must be at least warning severity, not silent.
        expect(
            preflight.exit_code_for(findings) >= 1,
            "expected exit code >= 1 for sibling-shared /tmp",
        )


def test_env_sync_run_classification():
    """Run-output mode produces ENV001 for env-sync error trace."""
    # We don't shell out — we call scan_run_output's inner classification
    # by invoking the regex path directly through a tiny shim.
    error_text = (
        "ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT\n"
        "Virtual environment changed while syncing"
    )
    expect(
        preflight.ENV_SYNC_RE.search(error_text) is not None,
        "ENV_SYNC_RE failed to match canonical env-sync error",
    )


def test_bsi_signature_regex():
    """BSI trustedTemp regex matches the exact thread signature."""
    canonical = (
        "/local_disk0/spark-d6bae111-42bd-4f54-9136-a4e9fbdec3d6/"
        "trustedTemp-55adadbe-d9ed-4278-a751-868797c1562f/tmpc58fz4pv"
    )
    expect(
        preflight.is_bsi_signature(canonical),
        f"is_bsi_signature() failed on canonical BSI path: {canonical}",
    )
    expect(
        not preflight.is_bsi_signature("/Volumes/main/x/y.parquet"),
        "is_bsi_signature() false-positive on a Volumes path",
    )


def test_exit_code_resolution():
    """exit_code_for follows blocker > warning > info > clean ordering."""
    expect(preflight.exit_code_for([]) == 0, "empty findings should exit 0")
    info = preflight.Finding("X", "info", "f", 1, "s", "m", "fix")
    warn = preflight.Finding("X", "warning", "f", 1, "s", "m", "fix")
    block = preflight.Finding("X", "blocker", "f", 1, "s", "m", "fix")
    expect(preflight.exit_code_for([info]) == 0, "info-only should exit 0")
    expect(preflight.exit_code_for([warn]) == 1, "warning should exit 1")
    expect(preflight.exit_code_for([block]) == 2, "blocker should exit 2")
    expect(
        preflight.exit_code_for([info, warn, block]) == 2,
        "mixed severities should exit at highest (2)",
    )


def test_json_output_shape():
    """--json output has findings and summary keys with correct counts."""
    findings = [
        preflight.Finding("A", "blocker", "f", 1, "s", "m", "fix"),
        preflight.Finding("B", "warning", "f", 2, "s", "m", "fix"),
        preflight.Finding("C", "info", "f", 3, "s", "m", "fix"),
    ]
    payload = json.loads(preflight.format_json(findings))
    expect("findings" in payload, "JSON output missing 'findings'")
    expect("summary" in payload, "JSON output missing 'summary'")
    expect(payload["summary"]["blocker"] == 1, "wrong blocker count")
    expect(payload["summary"]["warning"] == 1, "wrong warning count")
    expect(payload["summary"]["info"] == 1, "wrong info count")
    expect(payload["summary"]["total"] == 3, "wrong total count")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


TESTS = [
    test_bsi_pattern_blockers,
    test_clean_volumes_notebook,
    test_dab_yaml_shared_tmp,
    test_env_sync_run_classification,
    test_bsi_signature_regex,
    test_exit_code_resolution,
    test_json_output_shape,
]


def main() -> int:
    passed = 0
    failed: list[tuple[str, str]] = []
    for test in TESTS:
        try:
            test()
        except TestFailure as exc:
            failed.append((test.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed.append((test.__name__, f"unexpected error: {exc!r}"))
        else:
            passed += 1
            print(f"PASS  {test.__name__}")

    print()
    print(f"{passed}/{len(TESTS)} passed")
    if failed:
        print()
        for name, msg in failed:
            print(f"FAIL  {name}")
            print(f"      {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
