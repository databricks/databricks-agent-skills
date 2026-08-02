#!/usr/bin/env python3
"""Unit tests for the audit gate (scripts/audit_check.py).

These pin the *counting conventions*, not the corpus's current counts. A test
asserting "cross-skill traversals == 90" would fail the moment someone fixes
one, so every assertion here runs against a synthetic fixture skill instead.
The one exception is the registry smoke test, which only checks that each
finding still runs against the real repo and returns a list.

Stdlib-only; run with:
  python3 -m unittest discover -s tests -p "*_test.py"
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "audit_check", _REPO / "scripts" / "audit_check.py"
)
assert _spec is not None
assert _spec.loader is not None
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FixtureRepo:
    """A throwaway repo root with `skills/<name>/` laid out on disk."""

    def __init__(self, stack: tempfile.TemporaryDirectory):
        self.root = Path(stack.name)

    def skill(self, name: str, body: str, frontmatter: str = "") -> Path:
        skill_dir = self.root / "skills" / name
        _write(skill_dir / "SKILL.md", f"---\nname: {name}\n{frontmatter}---\n\n{body}")
        return skill_dir


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = FixtureRepo(self._tmp)


class ConventionTest(unittest.TestCase):
    """D6 / D9 / D1 — the definitions every count depends on."""

    def test_fences_are_blanked_and_line_count_is_preserved(self):
        text = "a\n```python\n../in-fence.md\n```\nb\n~~~\n../also.md\n~~~\nc"
        stripped = audit.strip_fences(text)
        self.assertEqual(len(stripped.split("\n")), len(text.split("\n")))
        self.assertNotIn("in-fence", stripped)
        self.assertNotIn("also", stripped)
        self.assertEqual(stripped.split("\n")[0], "a")
        self.assertEqual(stripped.split("\n")[4], "b")

    def test_indented_fence_is_still_a_fence(self):
        text = "intro\n    ```yaml\n    path: ../src/x.py\n    ```\nend"
        self.assertNotIn("../src", audit.strip_fences(text))

    def test_traversal_regex_ignores_ellipsis_truncation(self):
        # D9: 14 corpus occurrences are "/Volumes/.../file.csv"-style markers.
        self.assertTrue(audit._TRAVERSAL_RE.search("see ../references/x.md"))
        self.assertFalse(audit._TRAVERSAL_RE.search("dbfs:/Volumes/.../file.csv"))
        self.assertFalse(audit._TRAVERSAL_RE.search("/subscriptions/.../providers"))

    def test_tokens_round_rather_than_floor(self):
        # D6: floor division is what produced the audit's off-by-one drift.
        body = "x" * 4470  # 1117.5 tokens
        self.assertEqual(audit.body_tokens(body), 1118)
        self.assertEqual(audit.body_lines("one\ntwo\n\n"), 2)

    def test_frontmatter_is_excluded_from_the_body(self):
        body = audit.skill_body("---\nname: x\ndescription: y\n---\nz\n")
        self.assertEqual(body, "z\n")


class TraversalClassTest(unittest.TestCase):
    """D7 — classify by intent, not by where the path happens to resolve."""

    def setUp(self):
        self.names = {"databricks-apps", "databricks-lakebase"}

    def test_sibling_skill_is_cross_even_when_it_does_not_resolve(self):
        # The corpus's only broken links are one `../` short; they must not be
        # filed under intra just because they resolve inside their own skill.
        self.assertEqual(
            audit._classify_traversal("../databricks-lakebase/references/a.md", self.names),
            "cross",
        )

    def test_skills_prefix_is_transparent(self):
        for target in ("../../skills/databricks-apps/SKILL.md",
                       "../../../databricks-apps/references/a.md"):
            self.assertEqual(audit._classify_traversal(target, self.names), "cross")

    def test_own_skill_root_is_intra(self):
        self.assertEqual(audit._classify_traversal("../SKILL.md", self.names), "intra")


class TocTest(unittest.TestCase):
    """D8 — heading form, anchor form, and the 60-line window."""

    def test_heading_form(self):
        self.assertTrue(audit.has_toc("# Title\n\n## Table of Contents\n- a\n"))
        self.assertTrue(audit.has_toc("## Contents\n"))

    def test_anchor_form_needs_three(self):
        self.assertTrue(audit.has_toc("[a](#a)\n[b](#b)\n[c](#c)\n"))
        self.assertFalse(audit.has_toc("[a](#a)\n[b](#b)\n"))

    def test_signal_below_the_window_does_not_count(self):
        self.assertFalse(audit.has_toc("\n" * 70 + "## Table of Contents\n"))


class SpecTenBTest(FixtureTest):
    """SPEC-10b stays disjoint from NEW-C and ignores link display text."""

    def _skill_with(self, line: str) -> list[str]:
        skill = self.repo.skill("databricks-demo", line + "\n")
        _write(skill / "references" / "guide.md", "# Guide\n")
        _write(skill / "root-note.md", "# Root\n")
        return audit.check_spec_10b(self.repo.root)

    def test_backticked_bare_basename_is_a_defect(self):
        self.assertEqual(len(self._skill_with("Read `guide.md` first.")), 1)

    def test_bold_prose_bare_basename_is_a_defect(self):
        self.assertEqual(len(self._skill_with("1. **Read guide.md** - why")), 1)

    def test_prefixed_link_is_clean(self):
        self.assertEqual(self._skill_with("See [Guide](references/guide.md)."), [])

    def test_link_label_showing_the_filename_is_not_a_defect(self):
        self.assertEqual(
            self._skill_with("| [guide.md#x](references/guide.md#x) |"), []
        )

    def test_root_resolving_basename_belongs_to_new_c_not_here(self):
        self.assertEqual(self._skill_with("See [Root](root-note.md)."), [])

    def test_fenced_mention_is_exempt(self):
        self.assertEqual(self._skill_with("```\n`guide.md`\n```"), [])


class ReferenceScopeTest(FixtureTest):
    """PD-5 / PD-6 boundaries."""

    def test_pd6_covers_root_level_reference_files(self):
        # NEW-C's four root files are >100 lines with no TOC; scoping PD-6 to
        # references/ only is the exact blind spot NEW-C describes.
        skill = self.repo.skill("databricks-demo", "body\n")
        _write(skill / "long-root-note.md", "# Title\n" + "line\n" * 200)
        violations = audit.check_pd_6(self.repo.root)
        self.assertEqual(len(violations), 1)
        self.assertIn("long-root-note.md", violations[0])

    def test_pd6_ignores_short_and_toc_carrying_files(self):
        skill = self.repo.skill("databricks-demo", "body\n")
        _write(skill / "references" / "short.md", "# Short\n" + "line\n" * 10)
        _write(
            skill / "references" / "long.md",
            "# Long\n## Table of Contents\n" + "line\n" * 200,
        )
        self.assertEqual(audit.check_pd_6(self.repo.root), [])

    def test_pd5_flags_the_second_hop_only(self):
        skill = self.repo.skill("databricks-demo", "body\n")
        _write(skill / "references" / "b.md", "# B\n")
        _write(
            skill / "references" / "a.md",
            "# A\n"
            "[b](b.md)\n"                       # second hop  -> flagged
            "[self](a.md)\n"                    # self-link   -> exempt
            "[up](../SKILL.md)\n"               # leaves refs -> exempt here
            "[out](https://example.com/c.md)\n" # external    -> exempt
            "```\n[fenced](b.md)\n```\n",       # in fence    -> exempt
        )
        violations = audit.check_pd_5(self.repo.root)
        self.assertEqual(len(violations), 1)
        self.assertIn("a.md", violations[0])


class CompatTest(unittest.TestCase):
    """A body version literal only contradicts the pin when it is the CLI's."""

    def test_cli_claim_matches(self):
        self.assertEqual(
            audit._CLI_VERSION_CLAIM_RE.findall(
                "Install the Databricks CLI (>= v0.288.0) if not already installed:"
            ),
            ["v0.288.0"],
        )

    def test_library_pin_is_not_a_cli_claim(self):
        self.assertEqual(
            audit._CLI_VERSION_CLAIM_RE.findall("Databricks SDK for Python >= 0.81.0"),
            [],
        )


class GeneratedFreshnessTest(FixtureTest):
    """D14 — GEN-1 counts staleness against a fresh build, never edits.

    The fixtures use `manifest.json` because it is the one generated artifact
    that builds from `skills/` alone; the rest need `metaplugin/`, and the
    delegation test below covers those.
    """

    def _fresh_manifest(self) -> None:
        self.repo.skill("databricks-demo", "body\n", "description: Use when demoing.\n")
        (self.repo.root / "manifest.json").write_text(
            audit.serialize_manifest(audit.generate_manifest(self.repo.root))
        )

    def test_a_freshly_generated_artifact_is_clean(self):
        # The case the old edit-based guard got backwards: a regeneration commit
        # rewrites this file, and rewriting it is what makes it correct.
        self._fresh_manifest()
        self.assertEqual(audit._check_manifest_freshness(self.repo.root), [])

    def test_a_hand_edit_is_one_violation(self):
        self._fresh_manifest()
        path = self.repo.root / "manifest.json"
        path.write_text(path.read_text().replace('"version": "2"', '"version": "3"'))
        self.assertEqual(len(audit._check_manifest_freshness(self.repo.root)), 1)

    def test_source_moving_without_a_regenerate_is_one_violation(self):
        self._fresh_manifest()
        self.repo.skill("databricks-other", "body\n", "description: Use when other.\n")
        self.assertEqual(len(audit._check_manifest_freshness(self.repo.root)), 1)

    def test_a_missing_artifact_is_one_violation(self):
        self.repo.skill("databricks-demo", "body\n", "description: Use when demoing.\n")
        self.assertEqual(len(audit._check_manifest_freshness(self.repo.root)), 1)

    def test_unreadable_source_of_truth_reports_rather_than_raises(self):
        # House rule: every check_* returns list[str]. A fixture root has no
        # metaplugin/, and that has to read as one defect, not a traceback.
        violations = audit.check_gen_1(self.repo.root)
        self.assertEqual(len(violations), 1)
        self.assertIn(audit.META_FILE, violations[0])


class GenOneDelegationTest(unittest.TestCase):
    """GEN-1 and `skills.py validate` cannot disagree about what "generated" means."""

    def test_gen_1_is_exactly_the_generators_own_drift_checks(self):
        meta = audit.load_meta(_REPO)
        self.assertEqual(
            audit.check_gen_1(_REPO),
            [
                *audit.check_codex_metadata(_REPO),
                *audit.check_generated_plugins(_REPO, meta),
                *audit.check_generated_routing(_REPO, meta),
                *audit.check_generated_hooks(_REPO, meta),
                *audit._check_manifest_freshness(_REPO),
                *audit.check_generated_bundle(_REPO, meta),
            ],
        )


class RegistryTest(unittest.TestCase):
    """Every registered finding runs against the real corpus."""

    def test_ids_are_unique(self):
        ids = [finding[0] for finding in audit.FINDINGS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_check_returns_a_list_of_strings(self):
        for finding_id, _, _, check in audit.FINDINGS:
            with self.subTest(finding=finding_id):
                violations = check(_REPO)
                self.assertIsInstance(violations, list)
                for violation in violations:
                    self.assertIsInstance(violation, str)

    def test_severities_are_known(self):
        known = {audit.MUST_FIX, audit.ADVISORY, audit.BLOCKED, audit.ROLLUP}
        for _, severity, _, _ in audit.FINDINGS:
            self.assertIn(severity, known)


if __name__ == "__main__":
    unittest.main()
