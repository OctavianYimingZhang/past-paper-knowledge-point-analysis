#!/usr/bin/env python3
"""Orchestrator CLI for the past-paper knowledge-point analysis skill.

The skill is driven from `SKILL.md`. The SKILL delegates semantic work
(knowledge-point boundaries, pattern taxonomy, question-to-KP-pattern
mapping, tier narratives) to Claude Code subagents of varying sizes. This
CLI exposes the pure-Python stages those subagents call.

Subcommands:

    extract-papers      Parse every paper in the spec into raw questions.
    extract-lectures    Parse lecture material into candidate topics.
    extract-textbook    Parse textbook PDF into chapter / worked-example index.
    extract-answer-keys Parse DOCX answer keys into structured answer records.
    pattern-coverage    Compute per-pattern coverage statistics from
                        patterns.json + mapping.json.
    analyze             Run the Bayesian KP posterior, sensitivity, pattern
                        coverage (when wired) and the report writers.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Support running as ``python3 scripts/analyze_past_papers.py`` (module search
# path does not include the repo root) as well as ``python3 -m
# scripts.analyze_past_papers`` (it does).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.extract_answer_keys import extract_answer_key, dump_images
from scripts.extract_lectures import (
    compute_coverage_share,
    extract_lectures_from_pdf,
)
from scripts.extract_papers import load_paper_batch
from scripts.extract_textbook import extract_textbook, textbook_to_jsonable
from scripts.pattern_coverage import (
    compute_kp_pattern_coverage,
    coverage_to_jsonable,
)
from scripts.report_writer import write_docx, write_excel, write_json, write_markdown
from scripts.sensitivity import leave_one_out, sensitivity_sweep
from scripts.statistical_model import (
    YearObservation,
    analyze_kp,
    with_sensitivity_band,
)


DEFAULT_LAMBDA = 0.2
DEFAULT_TAU = 1.0
DEFAULT_ALPHA = 0.3
DEFAULT_LAMBDA_GRID = (0.0, 0.2, 0.4)
DEFAULT_TAU_GRID = (0.5, 1.0, 2.0)


def _load_spec(path: str) -> dict:
    spec_path = Path(path)
    if not spec_path.exists():
        raise SystemExit(f"spec not found: {spec_path}")
    return json.loads(spec_path.read_text())


def _ensure_output_dir(spec: dict) -> Path:
    out = Path(spec["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    return out


def cmd_extract_papers(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    out = _ensure_output_dir(spec)
    reports = load_paper_batch(spec["papers"])
    payload = {
        "course_id": spec["course_id"],
        "schema_version": 2,
        "papers": [
            {
                "year": r.year,
                "pdf_path": r.pdf_path,
                "total_pages": r.total_pages,
                "skipped_pages": list(r.skipped_pages),
                "has_negative_marking_notice": r.has_negative_marking_notice,
                "detected_style": r.detected_style,
                "warnings": list(r.warnings),
                "questions": [asdict(q) for q in r.questions],
            }
            for r in reports
        ],
    }
    dest = out / "extracted-papers.json"
    dest.write_text(json.dumps(payload, indent=2))
    print(f"wrote {dest}")
    return 0


def cmd_extract_lectures(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    out = _ensure_output_dir(spec)
    if not spec.get("notes_pdf"):
        raise SystemExit("extract-lectures requires a notes_pdf in the spec")
    report = extract_lectures_from_pdf(spec["notes_pdf"])
    coverage = compute_coverage_share(report)
    payload = {
        "course_id": spec["course_id"],
        "source_path": report.source_path,
        "total_pages": report.total_pages,
        "warnings": list(report.warnings),
        "lectures": [
            {
                "lecture_id": lecture.lecture_id,
                "title": lecture.title,
                "char_count": lecture.char_count,
                "source_pages": list(lecture.source_pages),
                "candidates": [
                    {
                        "topic_id": topic.topic_id,
                        "label": topic.label,
                        "bullet_context": list(topic.bullet_context),
                        "source_pages": list(topic.source_pages),
                    }
                    for topic in lecture.candidates
                ],
            }
            for lecture in report.lectures
        ],
    }
    lectures_dest = out / "extracted-lectures.json"
    lectures_dest.write_text(json.dumps(payload, indent=2))

    coverage_dest = out / "coverage.json"
    coverage_dest.write_text(
        json.dumps(
            {"coverage_version": 1, "coverage_shares": coverage},
            indent=2,
        )
    )
    print(f"wrote {lectures_dest}")
    print(f"wrote {coverage_dest}")
    return 0


def cmd_extract_textbook(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    out = _ensure_output_dir(spec)
    pdf_path = args.textbook or spec.get("textbook_pdf")
    if not pdf_path:
        raise SystemExit(
            "extract-textbook requires --textbook on the CLI or textbook_pdf in the spec"
        )
    report = extract_textbook(pdf_path)
    payload = {
        "course_id": spec["course_id"],
        "schema_version": 1,
        **textbook_to_jsonable(report),
    }
    dest = out / "extracted-textbook.json"
    dest.write_text(json.dumps(payload, indent=2))
    print(f"wrote {dest}")
    return 0


def cmd_extract_answer_keys(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    out = _ensure_output_dir(spec)
    image_root = out / "answer-key-images"
    results = []
    for record in spec.get("answer_keys", []):
        year = record["year"]
        docx = record["docx"]
        report = extract_answer_key(docx, year=year)
        image_dir = image_root / year
        dump_images(report, image_dir)
        results.append(
            {
                "year": year,
                "docx": docx,
                "warnings": list(report.warnings),
                "answers": [asdict(a) for a in report.answers],
                "images": [asdict(i) for i in report.images],
                "image_dir": str(image_dir),
            }
        )
    dest = out / "extracted-answer-keys.json"
    dest.write_text(json.dumps({"answer_keys": results}, indent=2))
    print(f"wrote {dest}")
    return 0


def cmd_pattern_coverage(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    out = _ensure_output_dir(spec)
    patterns_path = args.patterns or spec.get("patterns_path") or out / "patterns.json"
    mapping_path = args.mapping or spec.get("mapping_path")
    if not mapping_path:
        raise SystemExit(
            "pattern-coverage requires mapping_path in the spec or --mapping on the CLI"
        )
    if not Path(patterns_path).exists():
        raise SystemExit(f"patterns.json not found: {patterns_path}")
    reference_year = float(spec["reference_year"])
    lam = float(spec.get("lambda", DEFAULT_LAMBDA))
    alpha = float(args.alpha if args.alpha is not None else spec.get("alpha", DEFAULT_ALPHA))

    patterns_payload = json.loads(Path(patterns_path).read_text())
    mapping_payload = json.loads(Path(mapping_path).read_text())

    patterns_by_kp: dict[str, list[dict]] = {}
    for pattern in patterns_payload.get("patterns", []):
        patterns_by_kp.setdefault(pattern["kp_id"], []).append(pattern)

    questions_by_kp: dict[str, list[dict]] = {}
    for question in mapping_payload.get("questions", []):
        primary = question.get("primary_kp")
        if not primary:
            continue
        questions_by_kp.setdefault(primary, []).append(question)

    rows: list[dict] = []
    for kp_id, patterns in patterns_by_kp.items():
        coverages = compute_kp_pattern_coverage(
            kp_id=kp_id,
            patterns=patterns,
            mapping_questions=questions_by_kp.get(kp_id, []),
            reference_year=reference_year,
            lam=lam,
            alpha=alpha,
        )
        rows.extend(coverage_to_jsonable(c) for c in coverages)

    payload = {
        "course_id": spec["course_id"],
        "schema_version": 1,
        "hyperparameters": {
            "lambda": lam,
            "alpha": alpha,
            "reference_year": reference_year,
        },
        "rows": rows,
    }
    dest = out / "pattern-coverage.json"
    dest.write_text(json.dumps(payload, indent=2))
    print(f"wrote {dest}")
    return 0


def _load_mapping(path: str) -> dict[str, list[dict]]:
    mapping_payload = json.loads(Path(path).read_text())
    by_kp: dict[str, list[dict]] = {}
    for question in mapping_payload.get("questions", []):
        primary = question.get("primary_kp")
        if not primary:
            continue
        by_kp.setdefault(primary, []).append(question)
    return by_kp


def _load_coverage(path: str | None, kp_ids: list[str]) -> dict[str, float]:
    if not path:
        return {kp_id: 0.0 for kp_id in kp_ids}
    payload = json.loads(Path(path).read_text())
    shares = payload.get("coverage_shares", {})
    return {kp_id: float(shares.get(kp_id, 0.0)) for kp_id in kp_ids}


def _build_observations(
    kp_id: str,
    mapping: dict[str, list[dict]],
    papers: list[dict],
) -> list[YearObservation]:
    observations: list[YearObservation] = []
    primary_hits_by_year: dict[str, int] = {}
    for question in mapping.get(kp_id, []):
        year = str(question["year"])
        primary_hits_by_year[year] = primary_hits_by_year.get(year, 0) + 1

    for paper in papers:
        if paper.get("role", "formal") != "formal":
            continue
        year_label = str(paper["year"])
        try:
            year_int = int(float(year_label))  # tolerate "2023.4" floats
        except ValueError:
            continue
        hits = primary_hits_by_year.get(year_label, 0)
        total_questions = int(paper.get("expected_questions", 50))
        weight_override = paper.get("weight_override")
        observations.append(
            YearObservation(
                year=year_int,
                hit=hits > 0,
                total_questions=total_questions,
                hits_in_topic=hits,
                syllabus_version=paper.get("syllabus_version"),
                weight_override=(
                    float(weight_override) if weight_override is not None else None
                ),
            )
        )
    return observations


def _load_pattern_layer(
    spec: dict,
    out: Path,
    args: argparse.Namespace,
) -> tuple[dict[str, list[dict]] | None, dict[str, list[dict]] | None, dict[str, dict] | None]:
    """Best-effort load of the pattern layer artifacts.

    Returns (pattern_definitions, pattern_coverage, tier_narratives). Any
    missing artifact returns ``None`` for its slot so the DOCX writer can
    fall back to KP-only output.
    """
    patterns_path = args.patterns or spec.get("patterns_path") or out / "patterns.json"
    coverage_path = (
        args.pattern_coverage
        or spec.get("pattern_coverage_path")
        or out / "pattern-coverage.json"
    )
    narratives_path = spec.get("tier_narratives_path") or out / "tier-narratives.json"

    pattern_definitions: dict[str, list[dict]] | None = None
    pattern_coverage: dict[str, list[dict]] | None = None
    tier_narratives: dict[str, dict] | None = None

    if Path(patterns_path).exists():
        payload = json.loads(Path(patterns_path).read_text())
        pattern_definitions = {}
        for pattern in payload.get("patterns", []):
            pattern_definitions.setdefault(pattern["kp_id"], []).append(pattern)

    if Path(coverage_path).exists():
        payload = json.loads(Path(coverage_path).read_text())
        pattern_coverage = {}
        for row in payload.get("rows", []):
            pattern_coverage.setdefault(row["kp_id"], []).append(row)

    if Path(narratives_path).exists():
        payload = json.loads(Path(narratives_path).read_text())
        tier_narratives = payload.get("narratives") or {}

    return pattern_definitions, pattern_coverage, tier_narratives


def cmd_analyze(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    out = _ensure_output_dir(spec)

    mapping_path = args.mapping or spec.get("mapping_path")
    if not mapping_path:
        raise SystemExit(
            "analyze requires mapping_path in the spec or --mapping on the CLI"
        )
    coverage_path = args.coverage or spec.get("coverage_path")
    reference_year = int(spec["reference_year"])
    lam = float(spec.get("lambda", DEFAULT_LAMBDA))
    tau = float(spec.get("tau", DEFAULT_TAU))
    alpha = float(args.alpha if args.alpha is not None else spec.get("alpha", DEFAULT_ALPHA))
    lam_grid = tuple(float(x) for x in spec.get("lambda_grid", DEFAULT_LAMBDA_GRID))
    tau_grid = tuple(float(x) for x in spec.get("tau_grid", DEFAULT_TAU_GRID))
    lang = args.lang or spec.get("lang", "en")

    mapping = _load_mapping(mapping_path)
    kp_ids = sorted(mapping.keys())
    coverage = _load_coverage(coverage_path, kp_ids)

    posteriors = []
    sweeps = {}
    loo = {}
    for kp_id in kp_ids:
        observations = _build_observations(kp_id, mapping, spec["papers"])
        primary = analyze_kp(
            kp_id=kp_id,
            observations=observations,
            coverage_share=coverage.get(kp_id, 0.0),
            reference_year=reference_year,
            lam=lam,
            tau=tau,
        )
        sweep = sensitivity_sweep(
            kp_id=kp_id,
            observations=observations,
            coverage_share=coverage.get(kp_id, 0.0),
            reference_year=reference_year,
            lam_grid=lam_grid,
            tau_grid=tau_grid,
        )
        primary = with_sensitivity_band(primary, sweep.band)
        loo_result = leave_one_out(
            kp_id=kp_id,
            observations=observations,
            coverage_share=coverage.get(kp_id, 0.0),
            reference_year=reference_year,
            lam=lam,
            tau=tau,
        )
        posteriors.append(primary)
        sweeps[kp_id] = sweep
        loo[kp_id] = loo_result

    hyperparameters = {
        "course_id": spec["course_id"],
        "course_name": spec["course_name"],
        "reference_year": reference_year,
        "lambda": lam,
        "tau": tau,
        "alpha": alpha,
        "lambda_grid": list(lam_grid),
        "tau_grid": list(tau_grid),
        "lang": lang,
        "n_kp": len(posteriors),
        "n_papers": len([p for p in spec["papers"] if p.get("role", "formal") == "formal"]),
        "mapping_path": str(mapping_path),
        "coverage_path": str(coverage_path) if coverage_path else "derived-from-lectures",
    }

    pattern_definitions, pattern_coverage, tier_narratives = _load_pattern_layer(
        spec, out, args
    )

    excel_path = write_excel(
        out / f"{spec['course_id']}-analysis.xlsx", posteriors, sweeps, loo, hyperparameters
    )
    json_path = write_json(
        out / f"{spec['course_id']}-analysis.json", posteriors, sweeps, loo, hyperparameters
    )
    md_path = write_markdown(
        out / f"{spec['course_id']}-analysis.md", posteriors, sweeps, hyperparameters
    )
    docx_path = write_docx(
        out / f"{spec['course_id']}-analysis.docx",
        posteriors,
        sweeps,
        hyperparameters,
        pattern_coverage=pattern_coverage,
        pattern_definitions=pattern_definitions,
        tier_narratives=tier_narratives,
        lang=lang,
    )
    print(f"wrote {excel_path}")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"wrote {docx_path}")
    if pattern_definitions is None:
        print(
            "note: pattern layer not detected (no patterns.json / pattern-coverage.json); "
            "DOCX is KP-only. Run extract-textbook + pattern-architect + pattern-classifier "
            "+ pattern-coverage to enable Section B."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    extract_papers = sub.add_parser(
        "extract-papers",
        help="Parse past papers (MCQ or short-answer) into raw questions.",
    )
    extract_papers.add_argument("--spec", required=True, help="Path to a course spec JSON.")
    extract_papers.set_defaults(func=cmd_extract_papers)

    extract_lectures = sub.add_parser(
        "extract-lectures", help="Parse lecture material into candidate topics."
    )
    extract_lectures.add_argument("--spec", required=True)
    extract_lectures.set_defaults(func=cmd_extract_lectures)

    extract_textbook = sub.add_parser(
        "extract-textbook",
        help="Parse a textbook PDF into chapter index + worked-example seeds.",
    )
    extract_textbook.add_argument("--spec", required=True)
    extract_textbook.add_argument(
        "--textbook", help="Override the textbook PDF path from the spec."
    )
    extract_textbook.set_defaults(func=cmd_extract_textbook)

    extract_answer_keys = sub.add_parser(
        "extract-answer-keys",
        help="Parse DOCX answer keys into records and images.",
    )
    extract_answer_keys.add_argument("--spec", required=True)
    extract_answer_keys.set_defaults(func=cmd_extract_answer_keys)

    pattern_coverage = sub.add_parser(
        "pattern-coverage",
        help="Compute per-pattern coverage statistics from patterns.json + mapping.json.",
    )
    pattern_coverage.add_argument("--spec", required=True)
    pattern_coverage.add_argument("--patterns", help="Override patterns.json path.")
    pattern_coverage.add_argument("--mapping", help="Override mapping.json path.")
    pattern_coverage.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Novelty bias in [0, 1]. Default 0.3.",
    )
    pattern_coverage.set_defaults(func=cmd_pattern_coverage)

    analyze = sub.add_parser(
        "analyze",
        help="Run the Bayesian KP posterior, sensitivity, and report writers.",
    )
    analyze.add_argument("--spec", required=True)
    analyze.add_argument("--mapping", help="Override the mapping JSON path from the spec.")
    analyze.add_argument(
        "--coverage", help="Override the KP-level coverage JSON path from the spec."
    )
    analyze.add_argument(
        "--patterns",
        help="Override the patterns.json path. When present (alongside "
        "pattern-coverage.json), the DOCX includes Section B.",
    )
    analyze.add_argument(
        "--pattern-coverage",
        dest="pattern_coverage",
        help="Override the pattern-coverage.json path.",
    )
    analyze.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Novelty bias for the pattern layer. Default 0.3.",
    )
    analyze.add_argument(
        "--lang",
        choices=("en", "zh", "both"),
        default=None,
        help="Generated-report language (default 'en'). Markdown stays English.",
    )
    analyze.set_defaults(func=cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
