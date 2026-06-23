"""Shared fixtures for databricks-serverless-storage-check evaluation tests.

Unit tests (no marker) run at L1. Integration tests (@pytest.mark.integration) run at L2.
Environment variables are injected by the evaluator for integration tests:
  DATABRICKS_HOST, DATABRICKS_PROFILE, TEST_CATALOG, TEST_SCHEMA, WAREHOUSE_ID
"""

import os
from pathlib import Path

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: marks tests as integration tests (require Databricks)")


@pytest.fixture(scope="session")
def skill_dir():
    """Path to the skill directory (parent of eval/)."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def skill_md(skill_dir):
    """Contents of SKILL.md."""
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text()
    return ""


@pytest.fixture(scope="session")
def databricks_configured():
    """Skip tests if Databricks is not configured."""
    if not os.environ.get("DATABRICKS_HOST"):
        pytest.skip("DATABRICKS_HOST not set — run stf auth first")
    return True


@pytest.fixture(scope="session")
def workspace_client(databricks_configured):
    """Create a Databricks WorkspaceClient from environment."""
    from databricks.sdk import WorkspaceClient
    client = WorkspaceClient(
        host=os.environ.get("DATABRICKS_HOST"),
        profile=os.environ.get("DATABRICKS_PROFILE"),
    )
    client.current_user.me()
    return client


@pytest.fixture(scope="session")
def test_catalog():
    """Test catalog from environment."""
    return os.environ.get("TEST_CATALOG", "main")


@pytest.fixture(scope="session")
def test_schema():
    """Test schema from environment."""
    return os.environ.get("TEST_SCHEMA", "default")


@pytest.fixture(scope="session")
def warehouse_id():
    """SQL warehouse ID from environment."""
    wid = os.environ.get("WAREHOUSE_ID")
    if not wid:
        pytest.skip("WAREHOUSE_ID not set")
    return wid
