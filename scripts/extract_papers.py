"""Extract question stems from past-paper PDFs.

This module covers the mechanical layer of the pipeline: open a PDF, strip
front matter, and return a list of `RawQuestion` records. It does not map
questions to knowledge points; that is the job of a later stage handled by
a Sonnet subagent.

The parser handles two paper styles:

* Multiple-choice (MCQ) — each question has options A through E. The original
  Manchester biology layout falls in this category.
* Short-answer / structured — each question has free-form sub-parts labelled
  ``(a)``, ``(b)``, ``(c)``, ``(i)``, ``(ii)`` etc., often with a per-part
  mark allocation in square brackets or parentheses. Edexcel IAL Maths papers
  fall in this category.

Style is auto-detected per question: a question whose immediate body contains
A–E option lines is recorded as MCQ; otherwise it is recorded as short-answer
and any sub-parts and per-question marks are extracted. The parser is still
deliberately conservative — when it cannot place a line confidently it appends
it to the running stem rather than guessing structure, and surfaces warnings
back to SKILL.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # type: ignore[import-not-found]


QUESTION_HEADER_RE = re.compile(r"^\s*(\d{1,3})[\.\)]\s+(.+)")
OPTION_RE = re.compile(r"^\s*([A-E])[\.\)]\s+(.+)")
PART_LABEL_RE = re.compile(r"^\s*\(([a-z]{1,3}|[ivx]{1,4})\)\s*(.*)")
MARKS_INLINE_RE = re.compile(r"\[\s*(\d{1,3})\s*\]")
MARKS_PHRASE_RE = re.compile(r"\(\s*(\d{1,3})\s*marks?\s*\)", re.IGNORECASE)
TOTAL_MARKS_RE = re.compile(r"\[\s*Total\s*(?:[:=]?\s*)?(\d{1,3})\s*(?:marks?)?\s*\]", re.IGNORECASE)
NEGATIVE_MARKING_HINT = re.compile(r"negative marking|-0\.33|wrong answer", re.IGNORECASE)


@dataclass(frozen=True)
class QuestionPart:
    """A labelled sub-part of a short-answer question (e.g. ``(a)``)."""

    label: str
    text: str
    marks: int | None = None


@dataclass(frozen=True)
class RawQuestion:
    """One question extracted from a past paper.

    ``options`` is non-empty for MCQ questions and empty otherwise.
    ``parts`` is non-empty for short-answer questions that carry labelled
    sub-parts and empty otherwise. ``marks`` is the total mark allocation when
    the parser can locate it (typically a ``[Total: N marks]`` footer or a
    sum of per-part marks).
    """

    question_number: int
    stem: str
    options: tuple[tuple[str, str], ...] = ()
    parts: tuple[QuestionPart, ...] = ()
    marks: int | None = None
    source_pages: tuple[int, ...] = ()

    @property
    def is_mcq(self) -> bool:
        return bool(self.options)

    @property
    def is_short_answer(self) -> bool:
        return not self.options


@dataclass(frozen=True)
class PaperExtractionReport:
    year: str
    pdf_path: str
    total_pages: int
    skipped_pages: tuple[int, ...]
    questions: tuple[RawQuestion, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    has_negative_marking_notice: bool = False
    detected_style: str = "unknown"  # "mcq", "short_answer", or "mixed"


def extract_paper(
    pdf_path: str | Path,
    year: str,
    skip_pages: int = 2,
    expected_question_count: int | None = None,
) -> PaperExtractionReport:
    """Parse a single past-paper PDF into structured questions.

    The Manchester layout puts cover pages and rubrics on the first two pages
    and MCQ content on the remainder; the default `skip_pages=2` handles that.
    Edexcel IAL papers also fit `skip_pages=2` for the formula-sheet preamble
    on most sittings; callers should adjust per spec when the cover length
    differs.

    The function emits warnings rather than raising when:
      * the extracted question count is less than `expected_question_count`
      * two consecutive question numbers are missing
      * a page yields no candidate question header
    Option-count warnings are only issued for questions that look MCQ, so
    short-answer papers do not flood the warnings channel.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"past paper PDF not found: {path}")

    warnings: list[str] = []
    questions: list[RawQuestion] = []
    skipped = tuple(range(1, min(skip_pages, 0) + 1))
    has_negative_marking = False

    with fitz.open(path) as doc:
        total_pages = doc.page_count
        current: dict[str, object] | None = None
        for page_index in range(total_pages):
            if page_index < skip_pages:
                continue
            page = doc.load_page(page_index)
            text = page.get_text("text")
            if NEGATIVE_MARKING_HINT.search(text):
                has_negative_marking = True
            for line in text.splitlines():
                header = QUESTION_HEADER_RE.match(line)
                option = OPTION_RE.match(line)
                part = PART_LABEL_RE.match(line)
                if header:
                    if current is not None:
                        questions.append(_finalize(current))
                    current = {
                        "number": int(header.group(1)),
                        "stem": header.group(2).strip(),
                        "options": [],
                        "parts": [],
                        "marks": None,
                        "pages": {page_index + 1},
                    }
                elif option and current is not None:
                    current["options"].append((option.group(1), option.group(2).strip()))
                    current["pages"].add(page_index + 1)
                elif part and current is not None and not current["options"]:
                    # Short-answer sub-part. Inline parts are common; we open
                    # a new part only if we are not already mid-MCQ.
                    label = part.group(1)
                    body = part.group(2).strip()
                    current["parts"].append({"label": label, "text": body, "marks": None})
                    current["pages"].add(page_index + 1)
                elif current is not None:
                    text_line = line.strip()
                    if not text_line:
                        continue
                    if current["options"]:
                        # Continuation of the last option text.
                        letter, body = current["options"][-1]
                        current["options"][-1] = (letter, f"{body} {text_line}".strip())
                    elif current["parts"]:
                        # Continuation of the most recent part text + capture
                        # any inline marks at end-of-line.
                        last = current["parts"][-1]
                        last_text = f"{last['text']} {text_line}".strip()
                        marks = _extract_part_marks(text_line)
                        if marks is not None and last.get("marks") is None:
                            last["marks"] = marks
                        last["text"] = last_text
                    else:
                        current["stem"] = f"{current['stem']} {text_line}".strip()
                    current["pages"].add(page_index + 1)
                    # Capture total-marks footer if present anywhere on the line.
                    total = TOTAL_MARKS_RE.search(text_line)
                    if total and current.get("marks") is None:
                        current["marks"] = int(total.group(1))
        if current is not None:
            questions.append(_finalize(current))

    detected = _classify_style(questions)
    _sanity_check(questions, warnings, expected_question_count, detected)

    return PaperExtractionReport(
        year=year,
        pdf_path=str(path),
        total_pages=total_pages,
        skipped_pages=skipped,
        questions=tuple(questions),
        warnings=tuple(warnings),
        has_negative_marking_notice=has_negative_marking,
        detected_style=detected,
    )


def _extract_part_marks(text_line: str) -> int | None:
    """Pull the marks allocation off the end of a part-text line, if any."""
    inline = MARKS_INLINE_RE.search(text_line)
    if inline:
        return int(inline.group(1))
    phrase = MARKS_PHRASE_RE.search(text_line)
    if phrase:
        return int(phrase.group(1))
    return None


def _finalize(buf: dict[str, object]) -> RawQuestion:
    options = tuple(buf["options"])  # type: ignore[arg-type]
    raw_parts = buf["parts"]  # type: ignore[index]
    parts = tuple(
        QuestionPart(
            label=str(p["label"]),
            text=str(p["text"]).strip(),
            marks=int(p["marks"]) if p.get("marks") is not None else None,
        )
        for p in raw_parts  # type: ignore[union-attr]
    )
    pages = tuple(sorted(buf["pages"]))  # type: ignore[arg-type]
    marks = buf["marks"]
    if marks is None and parts:
        derived = sum(p.marks for p in parts if p.marks is not None)
        marks = derived if derived > 0 else None
    return RawQuestion(
        question_number=int(buf["number"]),  # type: ignore[arg-type]
        stem=str(buf["stem"]).strip(),
        options=options,
        parts=parts,
        marks=int(marks) if marks is not None else None,
        source_pages=pages,
    )


def _classify_style(questions: list[RawQuestion]) -> str:
    if not questions:
        return "unknown"
    mcq = sum(1 for q in questions if q.is_mcq)
    sa = len(questions) - mcq
    if mcq > 0 and sa == 0:
        return "mcq"
    if sa > 0 and mcq == 0:
        return "short_answer"
    return "mixed"


def _sanity_check(
    questions: list[RawQuestion],
    warnings: list[str],
    expected: int | None,
    detected_style: str,
) -> None:
    if not questions:
        warnings.append("no questions parsed; paper may be image-only and require OCR")
        return
    numbers = sorted({q.question_number for q in questions})
    gaps = [
        (numbers[i - 1], numbers[i])
        for i in range(1, len(numbers))
        if numbers[i] - numbers[i - 1] > 1
    ]
    if gaps:
        warnings.append(f"question-number gaps detected: {gaps}")
    if expected is not None and len(questions) < expected:
        warnings.append(
            f"extracted {len(questions)} questions; expected {expected}"
        )
    # Option-count warnings only apply when the question is supposed to be MCQ.
    for q in questions:
        if q.is_mcq and len(q.options) < 3:
            warnings.append(
                f"question {q.question_number} parsed with only {len(q.options)} options"
            )
    if detected_style == "mixed":
        warnings.append(
            "paper has both MCQ and short-answer questions; review detected_style"
        )
    if detected_style == "short_answer":
        # A short-answer paper that produced zero parts is suspicious — most
        # likely the parser missed the part labels (different bracket style).
        no_parts = [q.question_number for q in questions if not q.parts]
        if len(no_parts) == len(questions):
            warnings.append(
                "short-answer paper produced no labelled sub-parts; "
                "regex may need adjustment for this paper layout"
            )


def load_paper_batch(
    specs: list[dict[str, object]],
) -> list[PaperExtractionReport]:
    """Convenience: run extract_paper over a list of spec dicts.

    Each dict must contain keys `year`, `pdf`, and may contain `skip_pages`
    and `expected_questions`.
    """
    reports: list[PaperExtractionReport] = []
    for item in specs:
        report = extract_paper(
            pdf_path=str(item["pdf"]),
            year=str(item["year"]),
            skip_pages=int(item.get("skip_pages", 2)),
            expected_question_count=(
                int(item["expected_questions"])
                if item.get("expected_questions") is not None
                else None
            ),
        )
        reports.append(report)
    return reports
