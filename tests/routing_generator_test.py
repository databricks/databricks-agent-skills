#!/usr/bin/env python3
"""Tests for the routing generator (plugin.meta.json "routing" -> router + .mdc).

The product-skill routing table lives once in plugin.meta.json and is rendered
into both the prompt router's data (hooks/_routing_data.json) and the Cursor
rule (rules/databricks-routing.mdc). These tests pin two things:

1. The generated routing data equals the router's live values (STRONG /
   AMBIGUOUS / SUPPRESS / ROUTING_INSTRUCTION / ROUTING_REMINDER). This is the
   safety proof for the P2b cutover: because the generated data is byte-equal to
   what the router already uses, switching the router to load it changes nothing.
   (After the cutover these stay equal because the router loads exactly this.)
2. The two rendered routing tables (router instruction + .mdc) name the same
   skills, and every stable product skill is covered.

Stdlib-only; run with: python3 -m unittest discover -s tests -p "*_test.py"
"""
import importlib.util
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_skills_spec = importlib.util.spec_from_file_location(
    "skills", _REPO / "scripts" / "skills.py"
)
skills = importlib.util.module_from_spec(_skills_spec)
_skills_spec.loader.exec_module(skills)

_router_spec = importlib.util.spec_from_file_location(
    "databricks_router", _REPO / "hooks" / "databricks-router.py"
)
router = importlib.util.module_from_spec(_router_spec)
_router_spec.loader.exec_module(router)


class RoutingMatchesRouterTest(unittest.TestCase):
    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_strong_matches_router(self):
        self.assertEqual(self.meta["routing"]["strong"], list(router.STRONG))

    def test_ambiguous_matches_router(self):
        self.assertEqual(self.meta["routing"]["ambiguous"], list(router.AMBIGUOUS))

    def test_suppress_matches_router(self):
        self.assertEqual(self.meta["routing"]["suppress"], list(router.SUPPRESS))

    def test_rendered_instruction_matches_router(self):
        self.assertEqual(
            skills.render_routing_instruction(self.meta), router.ROUTING_INSTRUCTION
        )

    def test_reminder_matches_router(self):
        self.assertEqual(self.meta["routing"]["reminder"], router.ROUTING_REMINDER)


class GeneratedRoutingFilesTest(unittest.TestCase):
    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_rule_matches_disk(self):
        disk = (_REPO / "rules" / "databricks-routing.mdc").read_text()
        self.assertEqual(skills.render_routing_rule(self.meta), disk)

    def test_routing_files_not_drifted(self):
        self.assertEqual(skills.check_generated_routing(_REPO, self.meta), [])

    def test_routing_data_payload_shape(self):
        data = skills.build_routing_data(self.meta)
        for key in ("strong", "ambiguous", "suppress", "instruction", "reminder"):
            self.assertIn(key, data)


class RoutingCoverageTest(unittest.TestCase):
    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_coverage_clean(self):
        self.assertEqual(skills.check_routing_coverage(_REPO, self.meta), [])

    def test_required_skills_in_both_rendered_tables(self):
        instruction = skills.render_routing_instruction(self.meta)
        rule = skills.render_routing_rule(self.meta)
        table_skills = {row["skill"] for row in self.meta["routing"]["table"]}
        for skill_dir in skills.iter_skill_dirs(_REPO):
            name = skill_dir.name
            if name == "databricks-core":
                continue
            parent = skills._skill_parent(skill_dir)
            if parent in (None, "databricks-core"):
                self.assertIn(name, table_skills, f"{name} missing from routing table")
                self.assertIn(name, instruction, f"{name} missing from router instruction")
                self.assertIn(name, rule, f"{name} missing from Cursor rule")


if __name__ == "__main__":
    unittest.main()
