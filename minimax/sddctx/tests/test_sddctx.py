"""Unit tests for the SDD context module itself.

These tests do not need seekdb, PowerContext or MiniMax: they cover the pure
parts of the module (document parsing, source indexing, keyword extraction,
patch extraction) so a reviewer can check the module in isolation.
"""

from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sddctx.code_index import extract_symbols, extract_tests  # noqa: E402
from sddctx.documents import parse_document, parse_front_matter  # noqa: E402
from sddctx.minmax_client import MiniMaxClient  # noqa: E402
from sddctx.seekdb_store import SeekDBStore  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class TestFrontMatter(unittest.TestCase):
    def test_parses_scalars_and_lists(self):
        text = textwrap.dedent(
            """\
            ---
            spec_id: SPEC-1
            title: A title
            applies_to:
              - a.py
              - b.py
            ---

            body
            """
        )
        data, consumed = parse_front_matter(text)
        self.assertEqual(data["spec_id"], "SPEC-1")
        self.assertEqual(data["title"], "A title")
        self.assertEqual(data["applies_to"], ["a.py", "b.py"])
        self.assertGreater(consumed, 0)

    def test_without_front_matter_returns_empty(self):
        data, consumed = parse_front_matter("no front matter here\n")
        self.assertEqual(data, {})
        self.assertEqual(consumed, 0)


class TestDocumentParsing(unittest.TestCase):
    def test_sections_keep_id_title_body_and_source_line(self):
        document = parse_document(FIXTURES / "sample-spec.md")
        self.assertEqual(document.doc_id, "SPEC-TEST-001")
        ids = [section.section_id for section in document.sections]
        self.assertIn("R1", ids)
        self.assertIn("B1", ids)
        first = document.sections[0]
        self.assertEqual(first.title, "first requirement")
        self.assertIn("first body", first.body)
        self.assertEqual(first.kind, "requirement")
        self.assertGreater(first.source_line, 0)
        self.assertTrue(first.source_path.endswith("sample-spec.md"))

    def test_kind_is_derived_from_the_section_id_prefix(self):
        document = parse_document(FIXTURES / "sample-spec.md")
        kinds = {section.section_id: section.kind for section in document.sections}
        self.assertEqual(kinds["R1"], "requirement")
        self.assertEqual(kinds["B1"], "invariant")
        self.assertEqual(kinds["A1"], "acceptance")


class TestCodeIndex(unittest.TestCase):
    def test_extracts_functions_classes_and_methods(self):
        symbols = extract_symbols(FIXTURES / "sample_module.py", FIXTURES)
        by_name = {symbol.symbol: symbol for symbol in symbols}
        self.assertIn("top_level", by_name)
        self.assertIn("Helper", by_name)
        self.assertIn("Helper.method", by_name)
        self.assertEqual(by_name["top_level"].kind, "function")
        self.assertEqual(by_name["Helper"].kind, "class")
        self.assertEqual(by_name["Helper.method"].kind, "method")
        self.assertIn("def top_level", by_name["top_level"].signature)
        self.assertGreater(by_name["top_level"].source_line, 0)

    def test_extracts_test_cases(self):
        tests = extract_tests(FIXTURES / "sample_module.py", FIXTURES)
        names = {test.name for test in tests}
        self.assertIn("test_one", names)
        self.assertIn("test_two", names)
        for test in tests:
            self.assertTrue(test.test_id.startswith("sample_module.py::"))
            self.assertTrue(test.target)


class TestKeywordExtraction(unittest.TestCase):
    def test_deduplicates_and_keeps_order(self):
        keyword = SeekDBStore.keyword("matches regex matches filter", limit=10)
        self.assertEqual(keyword, "matches regex filter")

    def test_keeps_cjk_runs(self):
        keyword = SeekDBStore.keyword("正则 过滤 matches")
        self.assertIn("正则", keyword)
        self.assertIn("matches", keyword)

    def test_empty_input(self):
        self.assertEqual(SeekDBStore.keyword(""), "")


class TestPatchExtraction(unittest.TestCase):
    def test_strips_the_reasoning_block(self):
        answer = "<think>I should write a diff</think>\n\n```diff\n--- a/x\n+++ b/x\n```"
        patch = MiniMaxClient.extract_patch(answer)
        self.assertNotIn("<think>", patch)
        self.assertIn("--- a/x", patch)
        self.assertNotIn("```", patch)

    def test_accepts_a_language_tag_on_the_fence(self):
        answer = "```python\nprint(1)\n```"
        body = MiniMaxClient.extract_file(answer)
        self.assertEqual(body, "print(1)\n")

    def test_falls_back_to_the_raw_answer(self):
        answer = "plain answer without a fence"
        self.assertIn("plain answer", MiniMaxClient.extract_patch(answer))


if __name__ == "__main__":
    unittest.main()
