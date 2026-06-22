#!/usr/bin/env python3
"""Content guardrails for the experimental Iceberg skill."""

import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_ICEBERG_DIR = _REPO / "experimental" / "databricks-iceberg"


class IcebergContentTest(unittest.TestCase):
    def test_uniform_examples_recommend_iceberg_v3(self):
        text = "\n".join(path.read_text() for path in _ICEBERG_DIR.rglob("*.md"))

        self.assertIn("delta.enableIcebergCompatV3", text)
        self.assertNotIn("delta.enableIcebergCompatV2' = 'true", text)
        self.assertNotIn("delta.enableIcebergCompatV2\" = \"true", text)
        self.assertNotIn("ICEBERG_COMPAT_VERSION=2", text)


if __name__ == "__main__":
    unittest.main()
