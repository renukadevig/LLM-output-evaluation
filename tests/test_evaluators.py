"""Offline unit tests — no CLI/judge needed. Run:  python3 -m unittest -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llmval.core import EvalContext  # noqa: E402
from llmval.evaluators import dispatch  # noqa: E402
from llmval import jsonschema_mini  # noqa: E402


def ctx(output, **kw):
    return EvalContext(output=output, **kw)


class TestDeterministic(unittest.TestCase):
    def test_contains_all(self):
        r = dispatch({"type": "contains", "value": ["hello", "help"]}, ctx("hello, need help?"))
        self.assertEqual(r.status, "pass")

    def test_contains_missing(self):
        r = dispatch({"type": "contains", "value": ["bye"]}, ctx("hello"))
        self.assertEqual(r.status, "fail")

    def test_not_contains(self):
        r = dispatch({"type": "not_contains", "value": "error"}, ctx("all good"))
        self.assertEqual(r.status, "pass")

    def test_regex_should_match(self):
        r = dispatch({"type": "regex", "pattern": r"\d{3}"}, ctx("code 123"))
        self.assertEqual(r.status, "pass")

    def test_equals_case_insensitive(self):
        r = dispatch({"type": "equals", "value": "YES", "case_insensitive": True}, ctx(" yes "))
        self.assertEqual(r.status, "pass")

    def test_one_of(self):
        r = dispatch({"type": "one_of", "value": ["a", "b"]}, ctx("b"))
        self.assertEqual(r.status, "pass")

    def test_length_words(self):
        r = dispatch({"type": "max_length", "value": 2, "unit": "words"}, ctx("one two three"))
        self.assertEqual(r.status, "fail")

    def test_no_refusal_detects(self):
        r = dispatch({"type": "no_refusal"}, ctx("I'm sorry, I cannot help with that."))
        self.assertEqual(r.status, "fail")

    def test_no_pii_email(self):
        r = dispatch({"type": "no_pii"}, ctx("reach me at a@b.com"))
        self.assertEqual(r.status, "fail")
        self.assertIn("email", r.detail["found"])


class TestStructured(unittest.TestCase):
    def test_json_valid_fenced(self):
        r = dispatch({"type": "json_valid"}, ctx('```json\n{"a": 1}\n```'))
        self.assertEqual(r.status, "pass")

    def test_json_schema_ok(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
        r = dispatch({"type": "json_schema", "schema": schema}, ctx('{"a": 5}'))
        self.assertEqual(r.status, "pass")

    def test_json_schema_type_error(self):
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        r = dispatch({"type": "json_schema", "schema": schema}, ctx('{"a": "x"}'))
        self.assertEqual(r.status, "fail")

    def test_bool_is_not_integer(self):
        self.assertTrue(jsonschema_mini.validate(True, {"type": "integer"}))

    def test_json_path_equals(self):
        r = dispatch({"type": "json_path", "path": "items.0.id", "equals": 7},
                     ctx('{"items": [{"id": 7}]}'))
        self.assertEqual(r.status, "pass")

    def test_json_path_missing(self):
        r = dispatch({"type": "json_path", "path": "nope"}, ctx('{"a": 1}'))
        self.assertEqual(r.status, "fail")


class TestSimilarity(unittest.TestCase):
    def test_cosine_high(self):
        r = dispatch({"type": "similarity", "method": "cosine", "min_score": 0.3},
                     ctx("the cat sat", reference="the cat sat down"))
        self.assertEqual(r.status, "pass")

    def test_similarity_no_reference_errors(self):
        r = dispatch({"type": "similarity"}, ctx("x"))
        self.assertEqual(r.status, "error")

    def test_keyword_recall(self):
        r = dispatch({"type": "keyword_recall", "keywords": ["a", "z"], "min_ratio": 1.0},
                     ctx("a b c"))
        self.assertEqual(r.status, "fail")
        self.assertIn("z", r.detail["missing"])


class TestSemanticSimilarity(unittest.TestCase):
    def setUp(self):
        import llmval.embeddings  # noqa: F401 — register the check

    def test_registered(self):
        from llmval.evaluators import REGISTRY
        self.assertIn("semantic_similarity", REGISTRY)

    def test_no_reference_errors(self):
        r = dispatch({"type": "semantic_similarity"}, ctx("x"))
        self.assertEqual(r.status, "error")

    def test_skips_when_backend_unavailable(self):
        # force openai with no key present -> graceful skip, not fail
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        r = dispatch({"type": "semantic_similarity", "backend": "openai", "reference": "y"},
                     ctx("x"))
        self.assertEqual(r.status, "skip")


class TestJudgeDisabled(unittest.TestCase):
    def test_judge_skipped_when_backend_none(self):
        from llmval.suite import JudgeConfig
        r = dispatch({"type": "judge", "rubric": "tone"},
                     ctx("hi", judge=JudgeConfig(backend="none")))
        self.assertEqual(r.status, "skip")


if __name__ == "__main__":
    unittest.main()
