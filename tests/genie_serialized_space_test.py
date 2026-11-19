"""Exercise the Python helper agents copy from the Genie authoring reference."""

import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import uuid


REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "skills/databricks-genie-agents/references/create-genie-agent.md"
)


class GenieSerializedSpaceTest(unittest.TestCase):
    def setUp(self):
        blocks = [
            block
            for block in re.findall(r"```python\n(.*?)\n```", REFERENCE.read_text(), re.DOTALL)
            if "def build_serialized_space(" in block
        ]
        self.assertEqual(len(blocks), 1)
        namespace = {}
        exec(compile(blocks[0], str(REFERENCE), "exec"), namespace)
        self.build_serialized_space = namespace["build_serialized_space"]

    def test_sample_questions_preserve_requested_order_with_unsorted_uuids(self):
        questions = [
            "What is the headline?",
            "Which reason cluster explains it?",
            "Which node is affected?",
            "Who is the hero?",
            "What is the recommendation?",
            "What is the portfolio impact?",
            "What is the price impact?",
        ]
        # Force randomness out of order so the regression cannot pass by chance.
        with patch.object(uuid, "uuid4", side_effect=[uuid.UUID(int=n) for n in [7, 1, 6, 2, 5, 3, 4]]):
            payload = json.loads(self.build_serialized_space("catalog.schema.table", questions))

        samples = payload["config"]["sample_questions"]
        self.assertEqual([sample["question"] for sample in samples], [[q] for q in questions])
        ids = [sample["id"] for sample in samples]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), len(questions))
        for question_id in ids:
            self.assertRegex(question_id, r"^[0-9a-f]{32}$")

    def test_sample_question_iterables_preserve_duplicates_and_order(self):
        questions = ["First?", "Repeated?", "Repeated?", "Last?"]
        with patch.object(uuid, "uuid4", side_effect=[uuid.UUID(int=n) for n in [4, 2, 1, 3]]):
            payload = json.loads(self.build_serialized_space("catalog.schema.table", iter(questions)))

        samples = payload["config"]["sample_questions"]
        self.assertEqual([sample["question"] for sample in samples], [[q] for q in questions])
        self.assertEqual(len({sample["id"] for sample in samples}), len(questions))

    def test_optional_and_single_sample_questions(self):
        for questions in (None, []):
            with self.subTest(questions=questions):
                payload = json.loads(self.build_serialized_space("catalog.schema.table", questions))
                self.assertNotIn("config", payload)
        payload = json.loads(self.build_serialized_space("catalog.schema.table", ["Only question?"]))
        samples = payload["config"]["sample_questions"]
        self.assertEqual([sample["question"] for sample in samples], [["Only question?"]])
        self.assertEqual(uuid.UUID(hex=samples[0]["id"]).version, 4)

    def test_other_authoring_fields_keep_their_content(self):
        payload = json.loads(
            self.build_serialized_space(
                "catalog.schema.table",
                ["First?", "Second?"],
                instruction_rules=["Use dollars.", "Exclude cancellations."],
                example_sqls=[("Count?", "SELECT COUNT(*) FROM t"), ("Total?", "SELECT SUM(amount) FROM t")],
                column_configs=[{"column_name": "z"}, {"column_name": "a"}],
            )
        )
        self.assertEqual(payload["version"], 2)
        self.assertEqual(
            payload["data_sources"]["tables"],
            [{"identifier": "catalog.schema.table", "column_configs": [{"column_name": "a"}, {"column_name": "z"}]}],
        )
        instructions = payload["instructions"]
        self.assertEqual(instructions["text_instructions"][0]["content"], ["Use dollars.", "Exclude cancellations."])
        examples = instructions["example_question_sqls"]
        self.assertCountEqual(
            [(item["question"], item["sql"]) for item in examples],
            [(["Count?"], ["SELECT COUNT(*) FROM t"]), (["Total?"], ["SELECT SUM(amount) FROM t"])],
        )
        self.assertEqual([item["id"] for item in examples], sorted(item["id"] for item in examples))


if __name__ == "__main__":
    unittest.main()
