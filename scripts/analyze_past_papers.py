#!/usr/bin/env python3
"""Orchestrator CLI for the past-paper knowledge-point analysis skill.

The skill is driven from `SKILL.md`. The SKILL delegates semantic work
(knowledge-point boundaries, question-to-KP mapping, tier narratives) to
Claude Code subagents of varying sizes. This CLI exposes the pure-Python
stages those subagents call.

Subcommands:

    extract-papers      Parse every paper in the spec into raw questions.
    extract-lectures    Parse lecture material into candidate topics.
    extract-answer-keys Parse DOCX answer keys into structured answer records.
    analyze             Run the Bayesian posterior + sensitivity + reporting
                        stages. Requires a pre-computed mapping and coverage.
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
from scripts.report_writer import write_excel, write_json, write_markdown
from scripts.sensitivity import leave_one_out, sensitivity_sweep
from scripts.statistical_model import (
    YearObservation,
    analyze_kp,
    with_sensitivity_band,
)


DEFAULT_LAMBDA = 0.2
DEFAULT_TAU = 1.0
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
        "papers": [
            {
                "year": r.year,
                "pdf_path": r.pdf_path,
                "total_pages": r.total_pages,
                "skipped_pages": list(r.skipped_pages),
                "has_negative_marking_notice": r.has_negative_marking_notice,
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
            year_int = int(year_label)
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
    lam_grid = tuple(float(x) for x in spec.get("lambda_grid", DEFAULT_LAMBDA_GRID))
    tau_grid = tuple(float(x) for x in spec.get("tau_grid", DEFAULT_TAU_GRID))

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
        "lambda_grid": list(lam_grid),
        "tau_grid": list(tau_grid),
        "n_kp": len(posteriors),
        "n_papers": len([p for p in spec["papers"] if p.get("role", "formal") == "formal"]),
        "mapping_path": str(mapping_path),
        "coverage_path": str(coverage_path) if coverage_path else "derived-from-lectures",
    }
    excel_path = write_excel(
        out / f"{spec['course_id']}-analysis.xlsx", posteriors, sweeps, loo, hyperparameters
    )
    json_path = write_json(
        out / f"{spec['course_id']}-analysis.json", posteriors, sweeps, loo, hyperparameters
    )
    md_path = write_markdown(
        out / f"{spec['course_id']}-analysis.md", posteriors, sweeps, hyperparameters
    )
    print(f"wrote {excel_path}")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    extract_papers = sub.add_parser("extract-papers", help="Parse MCQ past papers into raw questions.")
    extract_papers.add_argument("--spec", required=True, help="Path to a course spec JSON.")
    extract_papers.set_defaults(func=cmd_extract_papers)

    extract_lectures = sub.add_parser("extract-lectures", help="Parse lecture material into candidate topics.")
    extract_lectures.add_argument("--spec", required=True)
    extract_lectures.set_defaults(func=cmd_extract_lectures)

    extract_answer_keys = sub.add_parser("extract-answer-keys", help="Parse DOCX answer keys into records and images.")
    extract_answer_keys.add_argument("--spec", required=True)
    extract_answer_keys.set_defaults(func=cmd_extract_answer_keys)

    analyze = sub.add_parser("analyze", help="Run the Bayesian posterior, sensitivity and report stages.")
    analyze.add_argument("--spec", required=True)
    analyze.add_argument("--mapping", help="Override the mapping JSON path from the spec")
    analyze.add_argument("--coverage", help="Override the coverage JSON path from the spec")
    analyze.set_defaults(func=cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
