"""Integration tests for databricks-serverless-storage-check.

These tests run at L2 and require a real Databricks workspace.
Environment variables are injected by the evaluator:
  DATABRICKS_HOST, DATABRICKS_PROFILE, TEST_CATALOG, TEST_SCHEMA, WAREHOUSE_ID
"""

import pytest


@pytest.mark.integration
class TestDatabricksConnectivity:
    """Verify basic Databricks workspace connectivity."""

    def test_workspace_reachable(self, workspace_client):
        """Can authenticate and reach the workspace."""
        user = workspace_client.current_user.me()
        assert user.user_name is not None

    def test_catalog_exists(self, workspace_client, test_catalog):
        """The configured test catalog exists."""
        catalogs = [c.name for c in workspace_client.catalogs.list()]
        assert test_catalog in catalogs, f"Catalog '{test_catalog}' not found"

    def test_schema_exists(self, workspace_client, test_catalog, test_schema):
        """The configured test schema exists."""
        schemas = [s.name for s in workspace_client.schemas.list(catalog_name=test_catalog)]
        assert test_schema in schemas, f"Schema '{test_schema}' not found in {test_catalog}"


@pytest.mark.integration
class TestWarehouse:
    """Verify SQL warehouse accessibility."""

    def test_warehouse_accessible(self, workspace_client, warehouse_id):
        """The configured SQL warehouse is accessible."""
        warehouse = workspace_client.warehouses.get(warehouse_id)
        assert warehouse is not None
        assert warehouse.state is not None
