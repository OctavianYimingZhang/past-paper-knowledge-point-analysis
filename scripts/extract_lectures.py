"""Extract discrete topic candidates from lecture slide decks or note PDFs.

Input is a course spec that either points at a directory of slides (PPTX
or PDF) or a single consolidated note PDF. Output is a list of lecture
records, each with a sequence of candidate knowledge points ready for the
Sonnet KP-boundary optimizer stage.

This module performs mechanical segmentation only. It does NOT decide
which candidates are distinct knowledge points; that is a semantic task
handed off to a subagent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # type: ignore[import-not-found]


LECTURE_HEADER_RE = re.compile(r"^\s*(?:lecture|l)[\s-]*(\d{1,3})\b[:\.\s-]*(.*)$", re.IGNORECASE)
NUMBERED_TOPIC_RE = re.compile(r"^\s*(\d+)[\.\)]\s+(.+)")
SUB_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.+)")


@dataclass(frozen=True)
class CandidateTopic:
    topic_id: str
    label: str
    bullet_context: tuple[str, ...]
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class Lecture:
    lecture_id: str
    title: str
    candidates: tuple[CandidateTopic, ...]
    char_count: int
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class LectureExtractionReport:
    source_path: str
    total_pages: int
    lectures: tuple[Lecture, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def extract_lectures_from_pdf(pdf_path: str | Path) -> LectureExtractionReport:
    """Walk a single consolidated lecture-notes PDF and extract lectures.

    Heuristics: a line matching `LECTURE_HEADER_RE` opens a new lecture.
    Numbered items inside a lecture become candidate topics. Bullet lines
    are attached as context to the most recent candidate.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"lecture PDF not found: {path}")

    warnings: list[str] = []
    lectures: list[Lecture] = []
    current_lecture: dict[str, object] | None = None
    current_topic: dict[str, object] | None = None

    with fitz.open(path) as doc:
        total_pages = doc.page_count
        for page_index in range(total_pages):
            page = doc.load_page(page_index)
            text = page.get_text("text")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                header = LECTURE_HEADER_RE.match(stripped)
                numbered = NUMBERED_TOPIC_RE.match(stripped)
                bullet = SUB_BULLET_RE.match(stripped)
                if header:
                    if current_topic is not None and current_lecture is not None:
                        current_lecture["topics"].append(_finalize_topic(current_lecture, current_topic))  # type: ignore[arg-type]
                        current_topic = None
                    if current_lecture is not None:
                        lectures.append(_finalize_lecture(current_lecture))
                    current_lecture = {
                        "number": int(header.group(1)),
                        "title": header.group(2).strip() or f"Lecture {header.group(1)}",
                        "topics": [],
                        "pages": {page_index + 1},
                        "char_count": 0,
                    }
                elif numbered and current_lecture is not None:
                    if current_topic is not None:
                        current_lecture["topics"].append(_finalize_topic(current_lecture, current_topic))  # type: ignore[arg-type]
                    current_topic = {
                        "number": int(numbered.group(1)),
                        "label": numbered.group(2).strip(),
                        "context": [],
                        "pages": {page_index + 1},
                    }
                    current_lecture["pages"].add(page_index + 1)  # type: ignore[attr-defined]
                elif bullet and current_topic is not None:
                    current_topic["context"].append(bullet.group(1).strip())
                elif current_topic is not None:
                    current_topic["context"].append(stripped)
                if current_lecture is not None:
                    current_lecture["char_count"] = int(current_lecture["char_count"]) + len(stripped)
        if current_topic is not None and current_lecture is not None:
            current_lecture["topics"].append(_finalize_topic(current_lecture, current_topic))  # type: ignore[arg-type]
        if current_lecture is not None:
            lectures.append(_finalize_lecture(current_lecture))

    if not lectures:
        warnings.append(
            "no lectures parsed; PDF may be image-based or use unconventional headings"
        )
    return LectureExtractionReport(
        source_path=str(path),
        total_pages=total_pages,
        lectures=tuple(lectures),
        warnings=tuple(warnings),
    )


def compute_coverage_share(report: LectureExtractionReport) -> dict[str, float]:
    """Return a dictionary topic_id -> share of total lecture character count.

    Coverage share is used as the regularization prior in the Bayesian
    model. The share is normalized across all topics in the report so they
    sum to 1.0 (up to floating-point slack).
    """
    weights: dict[str, int] = {}
    total = 0
    for lecture in report.lectures:
        for topic in lecture.candidates:
            weight = sum(len(ctx) for ctx in topic.bullet_context) + len(topic.label)
            weights[topic.topic_id] = weight
            total += weight
    if total <= 0:
        return {topic_id: 0.0 for topic_id in weights}
    return {topic_id: weight / total for topic_id, weight in weights.items()}


def _finalize_topic(
    lecture: dict[str, object],
    topic: dict[str, object],
) -> CandidateTopic:
    lecture_number = int(lecture["number"])  # type: ignore[arg-type]
    topic_number = int(topic["number"])  # type: ignore[arg-type]
    topic_id = f"L{lecture_number:02d}.{topic_number:02d}"
    return CandidateTopic(
        topic_id=topic_id,
        label=str(topic["label"]).strip(),
        bullet_context=tuple(topic["context"]),  # type: ignore[arg-type]
        source_pages=tuple(sorted(topic["pages"])),  # type: ignore[arg-type]
    )


def _finalize_lecture(lecture: dict[str, object]) -> Lecture:
    lecture_number = int(lecture["number"])  # type: ignore[arg-type]
    return Lecture(
        lecture_id=f"L{lecture_number:02d}",
        title=str(lecture["title"]).strip(),
        candidates=tuple(lecture["topics"]),  # type: ignore[arg-type]
        char_count=int(lecture["char_count"]),  # type: ignore[arg-type]
        source_pages=tuple(sorted(lecture["pages"])),  # type: ignore[arg-type]
    )
