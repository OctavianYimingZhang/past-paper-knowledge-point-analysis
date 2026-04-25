"""Unit tests for the textbook-extraction regex layer.

We do not test ``extract_textbook(pdf_path)`` end-to-end here because it
requires a real PDF fixture. Those regressions are caught by running the
CLI on an actual textbook in CI. These tests cover the regex contract
that the extractor depends on, and the dataclass-to-JSON serializer.
"""
from __future__ import annotations

from scripts.extract_textbook import (
    CHAPTER_HEADER_RE,
    Chapter,
    END_OF_BLOCK_RE,
    EXERCISE_HEADER_RE,
    ExerciseSet,
    SECTION_HEADER_RE,
    Section,
    TextbookExtractionReport,
    WORKED_EXAMPLE_RE,
    WorkedExample,
    textbook_to_jsonable,
)


class TestChapterHeader:
    def test_chapter_with_colon(self):
        m = CHAPTER_HEADER_RE.match("Chapter 5: Differentiation")
        assert m is not None
        assert m.group(1) == "5"
        assert m.group(2) == "Differentiation"

    def test_chapter_with_dash(self):
        m = CHAPTER_HEADER_RE.match("Chapter 12 - Integration techniques")
        assert m is not None
        assert m.group(1) == "12"

    def test_bare_number_and_title(self):
        m = CHAPTER_HEADER_RE.match("3 Vectors and forces")
        assert m is not None
        assert m.group(1) == "3"
        assert m.group(2) == "Vectors and forces"

    def test_lowercase_title_rejected(self):
        # Titles must start with a capital letter.
        m = CHAPTER_HEADER_RE.match("Chapter 5: differentiation")
        assert m is None


class TestSectionHeader:
    def test_two_part_section(self):
        m = SECTION_HEADER_RE.match("5.4 Implicit differentiation")
        assert m is not None
        assert m.group(1) == "5.4"
        assert m.group(2) == "Implicit differentiation"

    def test_section_with_long_title(self):
        m = SECTION_HEADER_RE.match("12.10 Integration by parts")
        assert m is not None
        assert m.group(1) == "12.10"


class TestWorkedExample:
    def test_basic_example(self):
        m = WORKED_EXAMPLE_RE.match("Example 12")
        assert m is not None
        assert m.group(1) == "12"

    def test_worked_example_phrase(self):
        m = WORKED_EXAMPLE_RE.match("Worked Example 3 Find dy/dx given ...")
        assert m is not None
        assert m.group(1) == "3"
        assert "Find dy/dx" in m.group(2)

    def test_case_insensitive(self):
        m = WORKED_EXAMPLE_RE.match("EXAMPLE 7")
        assert m is not None


class TestExerciseHeader:
    def test_lettered_exercise(self):
        m = EXERCISE_HEADER_RE.match("Exercise 5A")
        assert m is not None
        assert m.group(1) == "5A"

    def test_mixed_exercise(self):
        m = EXERCISE_HEADER_RE.match("Mixed Exercise 5")
        assert m is not None
        assert m.group(1) == "5"

    def test_practice_questions(self):
        m = EXERCISE_HEADER_RE.match("Practice Questions 1.2")
        assert m is not None
        assert m.group(1) == "1.2"


class TestEndOfBlock:
    def test_solution_terminates(self):
        assert END_OF_BLOCK_RE.match("Solution") is not None
        assert END_OF_BLOCK_RE.match("Solution:") is not None

    def test_answer_terminates(self):
        assert END_OF_BLOCK_RE.match("Answer:") is not None

    def test_random_text_does_not_terminate(self):
        assert END_OF_BLOCK_RE.match("Now consider the case y > 0") is None


class TestTextbookToJsonable:
    def _make_report(self) -> TextbookExtractionReport:
        chapter = Chapter(
            chapter_id="5",
            title="Differentiation",
            source_pages=(120, 121, 122),
            sections=(
                Section(
                    section_id="5.4",
                    title="Implicit differentiation",
                    source_pages=(125,),
                ),
            ),
            worked_examples=(
                WorkedExample(
                    example_id="5.E12",
                    chapter_id="5",
                    section_id="5.4",
                    label="Find tangent at (1, 2)",
                    body="Differentiate both sides ...",
                    source_pages=(126,),
                ),
            ),
            exercises=(
                ExerciseSet(
                    exercise_id="5.X5A",
                    chapter_id="5",
                    label="Implicit-differentiation drills",
                    source_pages=(130,),
                ),
            ),
        )
        return TextbookExtractionReport(
            source_path="/tmp/textbook.pdf",
            total_pages=420,
            chapters=(chapter,),
            warnings=(),
        )

    def test_payload_contains_expected_keys(self):
        payload = textbook_to_jsonable(self._make_report())
        assert payload["source_path"] == "/tmp/textbook.pdf"
        assert payload["total_pages"] == 420
        assert len(payload["chapters"]) == 1
        chapter = payload["chapters"][0]
        assert chapter["chapter_id"] == "5"
        assert chapter["worked_examples"][0]["example_id"] == "5.E12"
        assert chapter["worked_examples"][0]["section_id"] == "5.4"
        assert chapter["sections"][0]["section_id"] == "5.4"
        assert chapter["exercises"][0]["exercise_id"] == "5.X5A"
        assert payload["warnings"] == []

    def test_pages_list_serialization(self):
        payload = textbook_to_jsonable(self._make_report())
        chapter = payload["chapters"][0]
        assert chapter["source_pages"] == [120, 121, 122]
        assert chapter["sections"][0]["source_pages"] == [125]
