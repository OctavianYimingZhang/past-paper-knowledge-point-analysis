"""Parse DOCX answer keys into structured answer records.

Answer keys at Manchester are frequently scanned PDFs converted into DOCX
with the real content embedded as images. This module extracts what text
is present, pulls embedded images out so an OCR subagent can take them,
and returns a structured report that downstream code can merge with the
paper extraction output.

The module does NOT OCR. OCR of the extracted images is delegated to the
Haiku subagent defined in `agents/ocr-extractor.md`, because it needs
vision. This keeps the Python layer deterministic and cheap.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from docx import Document  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover
    Document = None  # type: ignore[assignment]
    _docx_import_error = exc
else:
    _docx_import_error = None


ANSWER_LINE_RE = re.compile(r"Q(?:uestion)?\s*(\d{1,3})\s*[:\.\-]\s*([A-E])", re.IGNORECASE)


@dataclass(frozen=True)
class AnswerRecord:
    question_number: int
    answer_letter: str | None
    explanation_text: str
    source: str  # "text" or "image"


@dataclass(frozen=True)
class EmbeddedImage:
    image_id: str
    suggested_filename: str
    sha256: str
    relative_path: str  # inside the docx zip


@dataclass(frozen=True)
class AnswerKeyExtractionReport:
    docx_path: str
    year: str
    answers: tuple[AnswerRecord, ...]
    images: tuple[EmbeddedImage, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def extract_answer_key(docx_path: str | Path, year: str) -> AnswerKeyExtractionReport:
    """Parse a DOCX answer key into text answers and referenced images.

    Text-extractable answers are parsed with a simple regex. Embedded
    images are enumerated so an OCR subagent can pick them up.
    """
    if _docx_import_error is not None:
        raise RuntimeError(
            "python-docx is required to parse answer keys; install via "
            "'pip install -r requirements.txt'"
        ) from _docx_import_error

    path = Path(docx_path)
    if not path.exists():
        raise FileNotFoundError(f"answer-key DOCX not found: {path}")

    warnings: list[str] = []
    answers: list[AnswerRecord] = []
    document = Document(str(path))
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        match = ANSWER_LINE_RE.search(text)
        if match:
            answers.append(
                AnswerRecord(
                    question_number=int(match.group(1)),
                    answer_letter=match.group(2).upper(),
                    explanation_text=text,
                    source="text",
                )
            )

    images = _enumerate_images(path, warnings)
    if not answers and not images:
        warnings.append(
            "no answers or images found; answer key may be unusable as evidence"
        )
    elif not answers and images:
        warnings.append(
            "no text answers parsed; delegate image OCR to the Haiku extractor"
        )

    return AnswerKeyExtractionReport(
        docx_path=str(path),
        year=year,
        answers=tuple(answers),
        images=tuple(images),
        warnings=tuple(warnings),
    )


def _enumerate_images(path: Path, warnings: list[str]) -> list[EmbeddedImage]:
    images: list[EmbeddedImage] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.startswith("word/media/"):
                    continue
                with zf.open(name) as fh:
                    data = fh.read()
                digest = hashlib.sha256(data).hexdigest()
                suggested = Path(name).name
                image_id = f"{path.stem}-{suggested}"
                images.append(
                    EmbeddedImage(
                        image_id=image_id,
                        suggested_filename=suggested,
                        sha256=digest,
                        relative_path=name,
                    )
                )
    except zipfile.BadZipFile:
        warnings.append("DOCX is not a valid zip archive; image enumeration skipped")
    return images


def dump_images(report: AnswerKeyExtractionReport, out_dir: str | Path) -> list[Path]:
    """Write embedded images to disk so the OCR subagent can read them.

    Returns the list of written file paths. The OCR stage is expected to
    write its results to a sibling directory that the orchestrator can
    collect.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(report.docx_path) as zf:
        for image in report.images:
            destination = out / image.suggested_filename
            with zf.open(image.relative_path) as src, destination.open("wb") as dst:
                dst.write(src.read())
            written.append(destination)
    return written
