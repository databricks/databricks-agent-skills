#!/usr/bin/env python3
"""Unit tests for the databricks-router UserPromptSubmit hook.

The router decides which prompts get steered into the Databricks skills, so its
precision is pinned here (over-routing is annoying; under-routing misses work).
Stdlib-only; run with: python3 hooks/databricks_router_test.py
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_strong_routes_even_with_alternative_platform(self):
        # "databricks" present -> route despite the alternative-platform mention.
        self.assertRoutes("migrate my tables from redshift to databricks")
        self.assertRoutes("migrate from snowflake to databricks")

    def test_new_strong_terms_route(self):
        self.assertRoutes("share this table via delta sharing")
        self.assertRoutes("ingest with the cloudFiles format")

    def test_new_ambiguous_terms(self):
        self.assertRoutes("create a serverless sql warehouse")
        self.assertRoutes("set up auto loader for streaming ingestion")
        self.assertSkips("set up a sql warehouse in snowflake")
        # One-word "autoloader" (PHP/composer style) must not match.
        self.assertSkips("fix the php autoloader config")

    def test_ambiguous_routes_without_alternative_platform(self):
        for p in [
            "set up a model serving endpoint",
            "create a vector search index for RAG",
            "build a medallion architecture for my tables",
            "ask Genie about revenue",
        ]:
            self.assertRoutes(p)

    def test_ambiguous_suppressed_by_alternative_platform(self):
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


class SessionMemoTest(unittest.TestCase):
    def test_first_route_full_then_reminder(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(router.tempfile, "gettempdir", return_value=tmp):
            first = router.routing_context("deploy a databricks job", "sess-1")
            second = router.routing_context("update that databricks job", "sess-1")
            other = router.routing_context("deploy a databricks job", "sess-2")
        self.assertEqual(first, router.ROUTING_INSTRUCTION)
        self.assertEqual(second, router.ROUTING_REMINDER)
        self.assertEqual(other, router.ROUTING_INSTRUCTION)

    def test_non_databricks_prompt_does_not_mark_session(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(router.tempfile, "gettempdir", return_value=tmp):
            self.assertIsNone(router.routing_context("hello there friend", "sess-3"))
            self.assertEqual(
                router.routing_context("deploy a databricks job", "sess-3"),
                router.ROUTING_INSTRUCTION,
            )

    def test_missing_session_id_always_full_instruction(self):
        for sid in (None, "", "!!!"):
            self.assertEqual(
                router.routing_context("deploy a databricks job", sid),
                router.ROUTING_INSTRUCTION,
            )


if __name__ == "__main__":
    unittest.main()
