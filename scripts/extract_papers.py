"""Extract MCQ question stems from past-paper PDFs.

This module covers the mechanical layer of the pipeline: open a PDF, strip
front matter, and return a list of `RawQuestion` records. It does not map
questions to knowledge points; that is the job of a later stage handled by
a Sonnet subagent.

The parser is deliberately conservative. If a page does not match the
expected MCQ layout it is reported back as a review issue rather than
guessed at. The SKILL.md orchestration layer decides how to recover.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # type: ignore[import-not-found]


QUESTION_HEADER_RE = re.compile(r"^\s*(\d{1,3})[\.\)]\s+(.+)")
OPTION_RE = re.compile(r"^\s*([A-E])[\.\)]\s+(.+)")
NEGATIVE_MARKING_HINT = re.compile(r"negative marking|-0\.33|wrong answer", re.IGNORECASE)


@dataclass(frozen=True)
class RawQuestion:
    question_number: int
    stem: str
    options: tuple[tuple[str, str], ...]
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class PaperExtractionReport:
    year: str
    pdf_path: str
    total_pages: int
    skipped_pages: tuple[int, ...]
    questions: tuple[RawQuestion, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    has_negative_marking_notice: bool = False


def extract_paper(
    pdf_path: str | Path,
    year: str,
    skip_pages: int = 2,
    expected_question_count: int | None = None,
) -> PaperExtractionReport:
    """Parse a single past-paper PDF into structured questions.

    The Manchester layout puts cover pages and rubrics on the first two pages
    and MCQ content on the remainder; the default `skip_pages=2` handles that.
    The function emits warnings rather than raising when:
      * the extracted question count is less than `expected_question_count`
      * two consecutive question numbers are missing
      * a page yields no candidate question header
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
                if header:
                    if current is not None:
                        questions.append(_finalize(current))
                    current = {
                        "number": int(header.group(1)),
                        "stem": header.group(2).strip(),
                        "options": [],
                        "pages": {page_index + 1},
                    }
                elif option and current is not None:
                    current["options"].append((option.group(1), option.group(2).strip()))
                    current["pages"].add(page_index + 1)
                elif current is not None:
                    text_line = line.strip()
                    if not text_line:
                        continue
                    if current["options"]:
                        # Continuation of the last option text
                        letter, body = current["options"][-1]
                        current["options"][-1] = (letter, f"{body} {text_line}".strip())
                    else:
                        current["stem"] = f"{current['stem']} {text_line}".strip()
                    current["pages"].add(page_index + 1)
        if current is not None:
            questions.append(_finalize(current))

    _sanity_check(questions, warnings, expected_question_count)

    return PaperExtractionReport(
        year=year,
        pdf_path=str(path),
        total_pages=total_pages,
        skipped_pages=skipped,
        questions=tuple(questions),
        warnings=tuple(warnings),
        has_negative_marking_notice=has_negative_marking,
    )


def _finalize(buf: dict[str, object]) -> RawQuestion:
    options = tuple(buf["options"])  # type: ignore[arg-type]
    pages = tuple(sorted(buf["pages"]))  # type: ignore[arg-type]
    return RawQuestion(
        question_number=int(buf["number"]),  # type: ignore[arg-type]
        stem=str(buf["stem"]).strip(),
        options=options,
        source_pages=pages,
    )


def _sanity_check(
    questions: list[RawQuestion],
    warnings: list[str],
    expected: int | None,
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
    for q in questions:
        if len(q.options) < 3:
            warnings.append(
                f"question {q.question_number} parsed with only {len(q.options)} options"
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
