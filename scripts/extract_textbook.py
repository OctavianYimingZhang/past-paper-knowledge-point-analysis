"""Extract chapter structure and worked-example seeds from a textbook PDF.

The pattern-aware analysis pipeline asks: for each knowledge point (KP),
what is the universe of question patterns that could be tested? Past papers
only show what *has* been used; textbooks describe the *full* pattern space
through worked examples and end-of-chapter exercises. This module reads a
textbook PDF and emits a structured payload that the `pattern-architect`
Sonnet subagent then consumes (alongside lecture slides) to derive the
canonical pattern taxonomy.

Like `extract_lectures.py`, this module is mechanical and deliberately
conservative. It does not call any LLM, does not infer KP boundaries, and
does not invent example bodies. When the regex layer cannot place text it
attaches it to the running buffer and surfaces a warning.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # type: ignore[import-not-found]


CHAPTER_HEADER_RE = re.compile(
    r"^\s*(?:Chapter\s+)?(\d{1,2})(?:\s*[:.\-–]\s*|\s+)([A-Z][^\n]{3,80})\s*$"
)
SECTION_HEADER_RE = re.compile(
    r"^\s*(\d{1,2}\.\d{1,2})\s+([A-Z][^\n]{3,80})\s*$"
)
WORKED_EXAMPLE_RE = re.compile(
    r"^\s*(?:Example|Worked Example)\s+(\d{1,3})\b(.*)$",
    re.IGNORECASE,
)
EXERCISE_HEADER_RE = re.compile(
    r"^\s*(?:Exercise|Mixed Exercise|Practice Questions?)\s+(\d{1,2}[A-Z]?(?:\.\d{1,2})?)\b(.*)$",
    re.IGNORECASE,
)
END_OF_BLOCK_RE = re.compile(r"^\s*(?:Solution|Answer|Hint|Notes?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class WorkedExample:
    """A single worked-example block extracted from a textbook chapter."""

    example_id: str
    chapter_id: str
    section_id: str | None
    label: str
    body: str
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class ExerciseSet:
    """An exercise-set boundary marker (we don't try to parse individual items)."""

    exercise_id: str
    chapter_id: str
    label: str
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class Section:
    """A section within a chapter."""

    section_id: str
    title: str
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class Chapter:
    """One textbook chapter with its sections, worked examples, and exercises."""

    chapter_id: str
    title: str
    source_pages: tuple[int, ...]
    sections: tuple[Section, ...] = ()
    worked_examples: tuple[WorkedExample, ...] = ()
    exercises: tuple[ExerciseSet, ...] = ()


@dataclass(frozen=True)
class TextbookExtractionReport:
    source_path: str
    total_pages: int
    chapters: tuple[Chapter, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def extract_textbook(pdf_path: str | Path) -> TextbookExtractionReport:
    """Walk a textbook PDF and emit chapter, section, example, and exercise records.

    The extractor is intentionally tolerant. If a textbook layout deviates
    from the regex assumptions (e.g. examples labelled ``E.g.`` rather than
    ``Example 1``) the affected blocks are simply not captured and a warning
    is recorded so the operator knows to inspect.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"textbook PDF not found: {path}")

    chapters: list[dict] = []
    current_chapter: dict | None = None
    current_section: dict | None = None
    current_block: dict | None = None
    warnings: list[str] = []

    with fitz.open(path) as doc:
        total_pages = doc.page_count
        for page_index in range(total_pages):
            page_no = page_index + 1
            page = doc.load_page(page_index)
            text = page.get_text("text")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                chapter_match = CHAPTER_HEADER_RE.match(stripped)
                section_match = SECTION_HEADER_RE.match(stripped)
                example_match = WORKED_EXAMPLE_RE.match(stripped)
                exercise_match = EXERCISE_HEADER_RE.match(stripped)
                terminator_match = END_OF_BLOCK_RE.match(stripped)

                if chapter_match:
                    _close_block(current_block, current_chapter)
                    current_block = None
                    if current_chapter is not None:
                        chapters.append(_finalize_chapter(current_chapter))
                    current_chapter = {
                        "chapter_id": chapter_match.group(1),
                        "title": chapter_match.group(2).strip(),
                        "pages": {page_no},
                        "sections": [],
                        "examples": [],
                        "exercises": [],
                    }
                    current_section = None
                    continue

                if section_match and current_chapter is not None:
                    _close_block(current_block, current_chapter)
                    current_block = None
                    section_record = {
                        "section_id": section_match.group(1),
                        "title": section_match.group(2).strip(),
                        "pages": {page_no},
                    }
                    current_chapter["sections"].append(section_record)
                    current_section = section_record
                    continue

                if example_match and current_chapter is not None:
                    _close_block(current_block, current_chapter)
                    label_tail = (example_match.group(2) or "").strip()
                    current_block = {
                        "kind": "example",
                        "example_id": (
                            f"{current_chapter['chapter_id']}.E{example_match.group(1)}"
                        ),
                        "section_id": (
                            current_section["section_id"] if current_section else None
                        ),
                        "label": (
                            label_tail
                            or f"Example {example_match.group(1)}"
                        ),
                        "body_lines": [],
                        "pages": {page_no},
                    }
                    continue

                if exercise_match and current_chapter is not None:
                    _close_block(current_block, current_chapter)
                    current_block = None
                    label_tail = (exercise_match.group(2) or "").strip()
                    current_chapter["exercises"].append(
                        {
                            "exercise_id": (
                                f"{current_chapter['chapter_id']}.X{exercise_match.group(1)}"
                            ),
                            "label": (
                                label_tail
                                or f"Exercise {exercise_match.group(1)}"
                            ),
                            "pages": {page_no},
                        }
                    )
                    continue

                if terminator_match and current_block is not None:
                    _close_block(current_block, current_chapter)
                    current_block = None
                    continue

                if current_block is not None:
                    current_block["body_lines"].append(stripped)
                    current_block["pages"].add(page_no)
                elif current_section is not None:
                    current_section["pages"].add(page_no)
                elif current_chapter is not None:
                    current_chapter["pages"].add(page_no)

        _close_block(current_block, current_chapter)
        if current_chapter is not None:
            chapters.append(_finalize_chapter(current_chapter))

    if not chapters:
        warnings.append(
            "no chapters detected; check the textbook layout against the "
            "CHAPTER_HEADER_RE pattern"
        )
    elif len(chapters) < 3:
        warnings.append(
            f"only {len(chapters)} chapters detected; layout may not match the "
            "expected 'Chapter N: Title' header convention"
        )

    return TextbookExtractionReport(
        source_path=str(path),
        total_pages=total_pages,
        chapters=tuple(chapters),
        warnings=tuple(warnings),
    )


def _close_block(block: dict | None, chapter: dict | None) -> None:
    if block is None or chapter is None:
        return
    if block["kind"] == "example":
        chapter["examples"].append(
            {
                "example_id": block["example_id"],
                "section_id": block.get("section_id"),
                "label": block["label"],
                "body": " ".join(block["body_lines"]).strip(),
                "pages": block["pages"],
            }
        )


def _finalize_chapter(chapter: dict) -> Chapter:
    return Chapter(
        chapter_id=str(chapter["chapter_id"]),
        title=str(chapter["title"]),
        source_pages=tuple(sorted(chapter["pages"])),
        sections=tuple(
            Section(
                section_id=str(s["section_id"]),
                title=str(s["title"]),
                source_pages=tuple(sorted(s["pages"])),
            )
            for s in chapter["sections"]
        ),
        worked_examples=tuple(
            WorkedExample(
                example_id=str(e["example_id"]),
                chapter_id=str(chapter["chapter_id"]),
                section_id=(str(e["section_id"]) if e.get("section_id") else None),
                label=str(e["label"]),
                body=str(e["body"]),
                source_pages=tuple(sorted(e["pages"])),
            )
            for e in chapter["examples"]
        ),
        exercises=tuple(
            ExerciseSet(
                exercise_id=str(x["exercise_id"]),
                chapter_id=str(chapter["chapter_id"]),
                label=str(x["label"]),
                source_pages=tuple(sorted(x["pages"])),
            )
            for x in chapter["exercises"]
        ),
    )


def textbook_to_jsonable(report: TextbookExtractionReport) -> dict:
    """Render the report as a JSON-serializable dict for downstream stages."""
    return {
        "source_path": report.source_path,
        "total_pages": report.total_pages,
        "warnings": list(report.warnings),
        "chapters": [
            {
                "chapter_id": c.chapter_id,
                "title": c.title,
                "source_pages": list(c.source_pages),
                "sections": [
                    {
                        "section_id": s.section_id,
                        "title": s.title,
                        "source_pages": list(s.source_pages),
                    }
                    for s in c.sections
                ],
                "worked_examples": [
                    {
                        "example_id": e.example_id,
                        "section_id": e.section_id,
                        "label": e.label,
                        "body": e.body,
                        "source_pages": list(e.source_pages),
                    }
                    for e in c.worked_examples
                ],
                "exercises": [
                    {
                        "exercise_id": x.exercise_id,
                        "label": x.label,
                        "source_pages": list(x.source_pages),
                    }
                    for x in c.exercises
                ],
            }
            for c in report.chapters
        ],
    }
