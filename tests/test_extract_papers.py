"""Unit tests for the relaxed paper-extraction parser.

These tests pin the behaviour the upgrade depends on:

* Auto-detection of paper style (mcq / short_answer / mixed).
* Sub-part label parsing for short-answer / structured papers.
* Per-part marks extraction from inline ``[N]`` and ``(N marks)`` tokens.
* Warnings raised when a short-answer paper produces no sub-parts.

We do not exercise ``extract_paper`` over a PDF here — those regressions
need real PDF fixtures and are caught when the CLI runs against the
benchmark suite. The unit tests target the helpers and dataclasses.
"""
from __future__ import annotations

from scripts.extract_papers import (
    MARKS_INLINE_RE,
    MARKS_PHRASE_RE,
    OPTION_RE,
    PART_LABEL_RE,
    QUESTION_HEADER_RE,
    QuestionPart,
    RawQuestion,
    TOTAL_MARKS_RE,
    _classify_style,
    _extract_part_marks,
    _sanity_check,
)


class TestQuestionHeader:
    def test_dotted_question(self):
        m = QUESTION_HEADER_RE.match("1. Find the gradient of y = x^2 at x = 3.")
        assert m is not None
        assert m.group(1) == "1"

    def test_paren_question(self):
        m = QUESTION_HEADER_RE.match("12) A particle moves with velocity v(t) = ...")
        assert m is not None
        assert m.group(1) == "12"

    def test_three_digit_question(self):
        m = QUESTION_HEADER_RE.match("100. Some long stem")
        assert m is not None
        assert m.group(1) == "100"


class TestOptionRegex:
    def test_a_through_e(self):
        for letter in "ABCDE":
            assert OPTION_RE.match(f"{letter}. some option") is not None

    def test_lowercase_option_rejected(self):
        # Options must be capital A-E.
        assert OPTION_RE.match("a. some option") is None


class TestPartLabel:
    def test_lower_letter_part(self):
        m = PART_LABEL_RE.match("(a) Find dy/dx")
        assert m is not None
        assert m.group(1) == "a"

    def test_roman_numeral_part(self):
        m = PART_LABEL_RE.match("(iii) State the value of k.")
        assert m is not None
        assert m.group(1) == "iii"

    def test_uppercase_letter_rejected(self):
        # Sub-parts use lowercase only — uppercase is reserved for MCQ options.
        assert PART_LABEL_RE.match("(A) Find ...") is None


class TestMarksRegex:
    def test_inline_brackets(self):
        m = MARKS_INLINE_RE.search("Show that... [4]")
        assert m is not None
        assert m.group(1) == "4"

    def test_marks_phrase(self):
        m = MARKS_PHRASE_RE.search("Differentiate the function (3 marks)")
        assert m is not None
        assert m.group(1) == "3"

    def test_total_marks_footer(self):
        m = TOTAL_MARKS_RE.search("[Total: 12 marks]")
        assert m is not None
        assert m.group(1) == "12"

    def test_total_marks_footer_short(self):
        m = TOTAL_MARKS_RE.search("[Total 7]")
        assert m is not None
        assert m.group(1) == "7"


class TestExtractPartMarks:
    def test_returns_inline_first(self):
        assert _extract_part_marks("show that ... [4]") == 4

    def test_falls_back_to_phrase(self):
        assert _extract_part_marks("differentiate (3 marks)") == 3

    def test_returns_none_when_absent(self):
        assert _extract_part_marks("show that this is true") is None


class TestClassifyStyle:
    def test_unknown_when_empty(self):
        assert _classify_style([]) == "unknown"

    def test_mcq_only(self):
        questions = [
            RawQuestion(
                question_number=1, stem="Q1",
                options=(("A", "alpha"), ("B", "beta")),
            ),
        ]
        assert _classify_style(questions) == "mcq"

    def test_short_answer_only(self):
        questions = [
            RawQuestion(
                question_number=1,
                stem="Q1",
                parts=(QuestionPart(label="a", text="find dy/dx"),),
            ),
        ]
        assert _classify_style(questions) == "short_answer"

    def test_mixed(self):
        questions = [
            RawQuestion(
                question_number=1, stem="Q1",
                options=(("A", "alpha"), ("B", "beta")),
            ),
            RawQuestion(
                question_number=2, stem="Q2",
                parts=(QuestionPart(label="a", text="show that"),),
            ),
        ]
        assert _classify_style(questions) == "mixed"


class TestSanityCheck:
    def test_no_questions_warns(self):
        warnings: list[str] = []
        _sanity_check([], warnings, expected=None, detected_style="unknown")
        assert any("no questions" in w for w in warnings)

    def test_question_gaps_warn(self):
        warnings: list[str] = []
        questions = [
            RawQuestion(question_number=1, stem="Q1"),
            RawQuestion(question_number=4, stem="Q4"),
        ]
        _sanity_check(questions, warnings, expected=None, detected_style="short_answer")
        assert any("gaps" in w for w in warnings)

    def test_short_answer_with_zero_parts_warns(self):
        warnings: list[str] = []
        questions = [
            RawQuestion(question_number=1, stem="Q1"),
            RawQuestion(question_number=2, stem="Q2"),
        ]
        _sanity_check(questions, warnings, expected=None, detected_style="short_answer")
        assert any("no labelled sub-parts" in w for w in warnings)

    def test_mcq_with_too_few_options_warns(self):
        warnings: list[str] = []
        questions = [
            RawQuestion(
                question_number=1, stem="Q1",
                options=(("A", "alpha"), ("B", "beta")),
            ),
        ]
        _sanity_check(questions, warnings, expected=None, detected_style="mcq")
        assert any("only 2 options" in w for w in warnings)

    def test_mcq_warning_does_not_fire_for_short_answer(self):
        warnings: list[str] = []
        questions = [
            RawQuestion(
                question_number=1, stem="Q1",
                parts=(QuestionPart(label="a", text="differentiate"),),
            ),
        ]
        _sanity_check(questions, warnings, expected=None, detected_style="short_answer")
        # SA papers should not generate option-count warnings.
        assert not any("options" in w for w in warnings)


class TestRawQuestion:
    def test_is_mcq_property(self):
        q = RawQuestion(question_number=1, stem="...", options=(("A", "alpha"),))
        assert q.is_mcq is True
        assert q.is_short_answer is False

    def test_is_short_answer_property(self):
        q = RawQuestion(
            question_number=1,
            stem="...",
            parts=(QuestionPart(label="a", text="..."),),
        )
        assert q.is_mcq is False
        assert q.is_short_answer is True

    def test_no_options_no_parts_treated_as_short_answer(self):
        q = RawQuestion(question_number=1, stem="...")
        assert q.is_short_answer is True
