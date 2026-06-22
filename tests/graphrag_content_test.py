#!/usr/bin/env python3
"""Content guardrails for the experimental GraphRAG skill."""

import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_GRAPHRAG_DIR = _REPO / "experimental" / "databricks-graphrag"


class GraphRAGContentTest(unittest.TestCase):
    def test_graphrag_skill_has_required_guidance(self):
        required_files = [
            _GRAPHRAG_DIR / "SKILL.md",
            _GRAPHRAG_DIR / "references" / "architecture-decisions.md",
            _GRAPHRAG_DIR / "references" / "retrieval-patterns.md",
            _GRAPHRAG_DIR / "references" / "evaluation-and-operations.md",
        ]
        for path in required_files:
            self.assertTrue(path.exists(), path)

        text = "\n".join(path.read_text() for path in required_files)
        for phrase in (
            "GraphRAG",
            "AI Search",
            "Unity Catalog",
            "Databricks Apps",
            "Model Serving",
            "MLflow",
            "Neo4j",
            "Text2Cypher",
            "hybrid",
            "reranker",
            "groundedness",
        ):
            self.assertIn(phrase, text)

        self.assertIn("Start with AI Search", text)


if __name__ == "__main__":
    unittest.main()
