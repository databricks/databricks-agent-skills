#!/usr/bin/env python3
"""Unit tests for the databricks-router UserPromptSubmit hook.

The router decides which prompts get steered into the Databricks skills, so its
precision is pinned here (over-routing is annoying; under-routing misses work).
Stdlib-only; run with: python3 hooks/databricks_router_test.py
"""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "databricks_router", Path(__file__).parent / "databricks-router.py"
)
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)


class CheckPromptTest(unittest.TestCase):
    def assertRoutes(self, prompt):
        self.assertIsNotNone(router.check_prompt(prompt), f"should route: {prompt!r}")

    def assertSkips(self, prompt):
        self.assertIsNone(router.check_prompt(prompt), f"should skip: {prompt!r}")

    def test_strong_routes(self):
        for p in [
            "How do I deploy a Databricks app?",
            "create a unity catalog grant on the sales schema",
            "set up a lakeflow job",
            "write this dataframe to dbfs",
            "validate my databricks.yml asset bundle",
            "deploy my dabs to the dev target",
            "build a delta live tables pipeline",
        ]:
            self.assertRoutes(p)

    def test_strong_routes_even_with_competitor(self):
        # "databricks" present -> route despite the competitor mention.
        self.assertRoutes("migrate my tables from redshift to databricks")

    def test_ambiguous_routes_without_competitor(self):
        for p in [
            "set up a model serving endpoint",
            "create a vector search index for RAG",
            "build a medallion architecture for my tables",
            "ask Genie about revenue",
        ]:
            self.assertRoutes(p)

    def test_ambiguous_suppressed_by_competitor(self):
        self.assertSkips("set up a model serving endpoint in sagemaker for redshift data")
        self.assertSkips("use bigquery for vector search")

    def test_local_dev_skips(self):
        for p in [
            "git commit -m 'fix'",
            "read the file src/main.py",
            "write a unit test for this function",
            "npm install react",
            "pip install requests",
            "build a docker image",
        ]:
            self.assertSkips(p)

    def test_unrelated_skips(self):
        for p in ["hello", "what's the weather", "refactor this react component", "ok",
                  "explain photon energy in physics"]:
            self.assertSkips(p)

    def test_too_short_skips(self):
        self.assertSkips("db")
        self.assertSkips("")

    def test_code_host_urls_do_not_route(self):
        # "databricks" as a GitHub org/repo name is not product intent.
        for p in [
            "review https://github.com/databricks/databricks-agent-skills/pull/128 please",
            "what changed in github.com/databricks/cli recently?",
            "clone git@github.com:databricks/terraform-provider-databricks.git",
        ]:
            self.assertSkips(p)

    def test_workspace_urls_still_route(self):
        # Hostname contains "databricks" -> real product signal.
        self.assertRoutes("why is https://myco.cloud.databricks.com/jobs/123 failing?")

    def test_url_plus_real_intent_routes(self):
        # Only the URL is blanked; intent outside it still routes.
        self.assertRoutes(
            "review https://github.com/databricks/cli/pull/5 and then deploy the databricks job"
        )

    def test_extract_prompt_shapes(self):
        self.assertEqual(router.extract_prompt({"prompt": "hi"}), "hi")
        self.assertEqual(router.extract_prompt({"message": "yo"}), "yo")
        self.assertEqual(router.extract_prompt({"prompt": {"content": "x"}}), "x")
        self.assertEqual(
            router.extract_prompt({"prompt": [{"text": "a"}, {"text": "b"}]}), "a b"
        )


if __name__ == "__main__":
    unittest.main()
