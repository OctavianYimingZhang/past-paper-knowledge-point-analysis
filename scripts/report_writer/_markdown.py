"""Markdown writer that mirrors the new DOCX layout.

Section order matches ``_docx.py`` exactly so the two formats stay in
sync. Tables are rendered as Markdown pipe tables. The Markdown writer
does not ship the page-break artefacts that the DOCX writer needs.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.pattern_coverage import PatternCoverage
from core.sensitivity import LeaveOneOutResult, SensitivitySweep
from core.statistical_model import KPPosterior
from ._common import (
    APPENDIX_AUDIT,
    APPENDIX_METHODOLOGY,
    APPENDIX_PATTERNS,
    KPCheatSheet,
    MAX_ALREADY_TESTED_ROWS,
    MAX_STILL_POSSIBLE_ROWS,
    SECTION_CHEAT_SHEETS,
    SECTION_EXEC_SUMMARY,
    SECTION_PREDICTIONS,
    SECTION_SENSITIVITY,
    build_sheets,
    caveat_bullets,
    confidence_chip,
    executive_headline,
    label_index,
    resolve_course_meta,
    sort_for_predictions_table,
    top_focus_kps,
    top_fresh_targets,
)


def write_markdown(
    out_path: str | Path,
    posteriors: list[KPPosterior],
    sweeps: dict[str, SensitivitySweep],
    hyperparameters: dict[str, object],
    *,
    pattern_coverage: list[PatternCoverage] | None = None,
    pattern_definitions: list[dict] | None = None,
    mapping_questions: list[dict] | None = None,
    kps: list[dict] | None = None,
    tier_narratives: dict | None = None,
    course_meta: dict | None = None,
    loo: dict[str, LeaveOneOutResult] | None = None,
) -> Path:
    """Write the executive-summary Markdown report."""
    path = Path(out_path)
    sheets = build_sheets(
        posteriors=posteriors,
        pattern_coverage=pattern_coverage,
        pattern_definitions=pattern_definitions,
        mapping_questions=mapping_questions,
        kps=kps,
        tier_narratives=tier_narratives,
    )
    course = resolve_course_meta(course_meta, hyperparameters, posteriors)

    lines: list[str] = []
    course_name = course.get("course_name", "Past-Paper Analysis")
    course_id = course.get("course_id", "course")
    lines.append(f"# {course_name} — Past-Paper Analysis")
    lines.append("")
    lines.append(
        f"_Course: {course_id} • Generated: "
        f"{datetime.now().isoformat(timespec='seconds')}_"
    )
    lines.append("")

    _md_executive_summary(lines, posteriors, sheets, course)
    _md_predictions_table(lines, posteriors, sheets)
    _md_kp_cheatsheets(lines, posteriors, sheets)
    _md_sensitivity_section(lines, posteriors, sweeps, loo)
    _md_full_kp_audit(lines, posteriors)
    _md_pattern_catalogue(lines, pattern_coverage, pattern_definitions)
    _md_methodology(lines, hyperparameters)

    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _md_executive_summary(
    lines: list[str],
    posteriors: list[KPPosterior],
    sheets: dict[str, KPCheatSheet] | None,
    course: dict,
) -> None:
    lines.append(f"## {SECTION_EXEC_SUMMARY}")
    lines.append("")
    lines.append(executive_headline(posteriors, course, sheets))
    lines.append("")
    lines.append("**Top focus KPs**")
    lines.append("")
    lines.append("| KP | Tier | Posterior | Headline pattern |")
    lines.append("|----|------|-----------|------------------|")
    focus = top_focus_kps(posteriors, sheets)
    if not focus:
        lines.append("| _no anchor or core KPs detected_ | | | |")
    for posterior, sheet in focus:
        label = sheet.kp_label if sheet else posterior.kp_id
        headline_pattern = "—"
        if sheet and sheet.dominant_pattern is not None:
            dom = sheet.dominant_pattern
            headline_pattern = f"{dom.pattern_id} — {dom.pattern_label}"
        lines.append(
            f"| {posterior.kp_id} — {label} | {posterior.tier} | "
            f"{posterior.posterior_mean:.2f} "
            f"[{posterior.ci_lower_95:.2f}, {posterior.ci_upper_95:.2f}] "
            f"| {headline_pattern} |"
        )
    lines.append("")
    lines.append("**Top fresh patterns to drill**")
    lines.append("")
    lines.append("| KP | Pattern | Why fresh | Source |")
    lines.append("|----|---------|-----------|--------|")
    fresh = top_fresh_targets(sheets)
    if not fresh:
        lines.append("| _no fresh patterns flagged_ | | | |")
    for sheet, variant in fresh:
        sources = "; ".join(variant.sources) if variant.sources else "—"
        lines.append(
            f"| {sheet.kp_id} | {variant.pattern_id} — {variant.pattern_label} "
            f"| {variant.rationale} | {sources} |"
        )
    lines.append("")
    bullets = caveat_bullets(posteriors)
    if bullets:
        lines.append("**Biggest caveats**")
        lines.append("")
        for b in bullets:
            lines.append(f"- {b}")
        lines.append("")


def _md_predictions_table(
    lines: list[str],
    posteriors: list[KPPosterior],
    sheets: dict[str, KPCheatSheet] | None,
) -> None:
    lines.append(f"## {SECTION_PREDICTIONS}")
    lines.append("")
    lines.append("| KP ID | Label | Hits / Papers | Tier | Confidence |")
    lines.append("|-------|-------|---------------|------|------------|")
    for posterior in sort_for_predictions_table(posteriors):
        sheet = sheets.get(posterior.kp_id) if sheets else None
        label = sheet.kp_label if sheet and sheet.kp_label else posterior.kp_id
        lines.append(
            f"| {posterior.kp_id} | {label} "
            f"| {posterior.raw_hits}/{posterior.n_papers} "
            f"| {posterior.tier} | {confidence_chip(posterior)} |"
        )
    lines.append("")


def _md_kp_cheatsheets(
    lines: list[str],
    posteriors: list[KPPosterior],
    sheets: dict[str, KPCheatSheet] | None,
) -> None:
    lines.append(f"## {SECTION_CHEAT_SHEETS}")
    lines.append("")
    if not sheets:
        lines.append(
            "_No pattern data available for this run. Run extract-textbook + "
            "pattern-architect + pattern-classifier + pattern-coverage to "
            "enable per-KP cheat-sheets._"
        )
        lines.append("")
        return
    primary = [p for p in posteriors if p.tier in ("anchor", "core")]
    primary.sort(key=lambda p: (-p.posterior_mean, p.kp_id))
    if primary:
        focus = primary
    else:
        fallback = [
            p for p in posteriors if p.tier in ("emerging", "oneoff", "legacy")
        ]
        fallback.sort(key=lambda p: (-p.posterior_mean, p.kp_id))
        focus = fallback
        if focus:
            lines.append(
                "_No anchor or core KPs detected; falling back to the "
                "highest-posterior KPs that did appear in the data._"
            )
            lines.append("")
    if not focus:
        lines.append("_No KPs with exam evidence; only curriculum-only inferences._")
        lines.append("")
        return
    for posterior in focus:
        sheet = sheets.get(posterior.kp_id)
        if sheet is None:
            continue
        _md_render_cheatsheet(lines, sheet)


def _md_render_cheatsheet(lines: list[str], sheet: KPCheatSheet) -> None:
    lines.append(f"### {sheet.kp_id} — {sheet.kp_label}  [{sheet.tier}]")
    lines.append("")
    if sheet.lecture_ref:
        lines.append(f"_({sheet.lecture_ref})_")
        lines.append("")
    if sheet.headline:
        lines.append(sheet.headline)
        lines.append("")
    if sheet.narrative:
        lines.append(sheet.narrative)
        lines.append("")
    lines.append("**How it will be tested**")
    lines.append("")
    if sheet.dominant_pattern is not None:
        dom = sheet.dominant_pattern
        lines.append(
            f"_Dominant pattern_: **{dom.pattern_id} — {dom.pattern_label}**. "
            f"{dom.rationale}."
        )
        lines.append("")
        if dom.solution_sketch:
            for step in dom.solution_sketch:
                lines.append(f"- {step}")
            lines.append("")
    saturated_ids = ", ".join(v.pattern_id for v in sheet.saturated_patterns) or "—"
    fresh_ids = ", ".join(v.pattern_id for v in sheet.fresh_patterns) or "—"
    dormant_ids = ", ".join(v.pattern_id for v in sheet.dormant_patterns) or "—"
    lines.append(
        f"_Saturated_: {saturated_ids}. _Fresh_: {fresh_ids}. "
        f"_Dormant_: {dormant_ids}."
    )
    lines.append("")
    lines.append("**Already tested**")
    lines.append("")
    if sheet.already_tested:
        lines.append("| Year/Sitting | Q | Pattern | Prompt summary |")
        lines.append("|--------------|---|---------|-----------------|")
        for ex in sheet.already_tested[:MAX_ALREADY_TESTED_ROWS]:
            prompt = (ex.prompt_summary or "").replace("|", "\\|")
            lines.append(
                f"| {ex.year_label} | Q{ex.question_number} "
                f"| {ex.pattern_id} | {prompt or '—'} |"
            )
    else:
        lines.append("_No recorded occurrences._")
    lines.append("")
    lines.append("**Still possible**")
    lines.append("")
    if sheet.still_possible:
        lines.append("| Pattern | Why it's possible | Source |")
        lines.append("|---------|-------------------|--------|")
        for variant in sheet.still_possible[:MAX_STILL_POSSIBLE_ROWS]:
            sources = "; ".join(variant.sources) if variant.sources else "—"
            lines.append(
                f"| {variant.pattern_id} — {variant.pattern_label} "
                f"| {variant.rationale} | {sources} |"
            )
    else:
        lines.append("_No fresh or saturated-with-unseen patterns flagged._")
    lines.append("")
    lines.append("**Drill set**")
    lines.append("")
    if sheet.drill_set:
        for item in sheet.drill_set:
            lines.append(f"- {item}")
    else:
        lines.append("_No drill set assembled._")
    lines.append("")
    if sheet.open_caveats:
        lines.append(f"_Caveats: {' | '.join(sheet.open_caveats)}_")
        lines.append("")


def _md_sensitivity_section(
    lines: list[str],
    posteriors: list[KPPosterior],
    sweeps: dict[str, SensitivitySweep],
    loo: dict[str, LeaveOneOutResult] | None,
) -> None:
    lines.append(f"## {SECTION_SENSITIVITY}")
    lines.append("")
    unstable = [p for p in posteriors if p.sensitivity_band == "unstable"]
    if unstable:
        lines.append("**Unstable KPs**")
        lines.append("")
        lines.append("| KP | Label | Sensitivity band | Distinct sweep tiers |")
        lines.append("|----|-------|------------------|----------------------|")
        for p in unstable:
            sweep = sweeps.get(p.kp_id) if isinstance(sweeps, dict) else None
            distinct = ", ".join(sweep.distinct_tiers) if sweep else "?"
            lines.append(
                f"| {p.kp_id} | {p.kp_id} | {p.sensitivity_band} | {distinct} |"
            )
        lines.append("")
    if loo:
        flips = [r for r in loo.values() if r.tier_flips or r.max_abs_shift > 0.0]
        if flips:
            lines.append("**Leave-one-out shifts**")
            lines.append("")
            lines.append("| KP | Max |Δposterior| | Flipped year |")
            lines.append("|----|--------------------|--------------|")
            for r in flips:
                flipped = ", ".join(str(y) for y in r.tier_flips) or "—"
                lines.append(
                    f"| {r.kp_id} | {r.max_abs_shift:.3f} | {flipped} |"
                )
            lines.append("")
    warned = [p for p in posteriors if p.warnings]
    if warned:
        lines.append("**KPs with warnings**")
        lines.append("")
        lines.append("| KP | Warnings |")
        lines.append("|----|----------|")
        for p in warned:
            joined = "; ".join(p.warnings)
            lines.append(f"| {p.kp_id} | {joined} |")
        lines.append("")


def _md_full_kp_audit(lines: list[str], posteriors: list[KPPosterior]) -> None:
    lines.append(f"## {APPENDIX_AUDIT}")
    lines.append("")
    headers = [
        "kp_id",
        "tier",
        "posterior_mean",
        "ci_lower",
        "ci_upper",
        "raw_hits",
        "weighted_hits",
        "lambda_used",
        "tau_used",
        "trend_label",
        "trend_delta",
        "sensitivity_band",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for p in posteriors:
        row = [
            p.kp_id,
            p.tier,
            f"{p.posterior_mean:.3f}",
            f"{p.ci_lower_95:.3f}",
            f"{p.ci_upper_95:.3f}",
            str(p.raw_hits),
            f"{p.weighted_hits:.3f}",
            str(p.lambda_used),
            str(p.tau_used),
            p.trend_label,
            f"{p.trend_delta:.3f}",
            p.sensitivity_band,
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")


def _md_pattern_catalogue(
    lines: list[str],
    pattern_coverage: list[PatternCoverage] | None,
    pattern_definitions: list[dict] | None,
) -> None:
    lines.append(f"## {APPENDIX_PATTERNS}")
    lines.append("")
    if not pattern_coverage and not pattern_definitions:
        lines.append("_No pattern layer supplied._")
        lines.append("")
        return
    headers = [
        "kp_id",
        "pattern_id",
        "label",
        "raw_hits",
        "weighted_hits",
        "last_seen_year",
        "saturation_index",
        "freshness_flag",
        "predicted_score",
        "tier",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    label_lookup = label_index(pattern_definitions)
    rows = sorted(
        pattern_coverage or [],
        key=lambda c: (c.kp_id, c.pattern_id),
    )
    for c in rows:
        last_seen = "—" if c.last_seen_year is None else f"{c.last_seen_year}"
        lines.append(
            "| "
            + " | ".join(
                [
                    c.kp_id,
                    c.pattern_id,
                    label_lookup.get(c.pattern_id, ""),
                    str(c.raw_hits),
                    f"{c.weighted_hits:.3f}",
                    last_seen,
                    f"{c.saturation_index:.3f}",
                    "yes" if c.freshness_flag else "no",
                    f"{c.predicted_score:.3f}",
                    c.tier or "—",
                ]
            )
            + " |"
        )
    lines.append("")


def _md_methodology(lines: list[str], hyperparameters: dict) -> None:
    lines.append(f"## {APPENDIX_METHODOLOGY}")
    lines.append("")
    lines.append(
        "**KP layer.** The per-KP probability of appearing on the next sitting "
        "is a moment-matched Beta posterior over recency-weighted hits. Each "
        "year is weighted by `exp(-lambda * (reference_year - year))`. The "
        "prior is `Beta(tau * coverage, tau * (1 - coverage))` with `tau` "
        "capped at 2.0; this is a regularization prior, not an empirical one. "
        "The 95% credible interval is reported alongside the posterior mean. "
        "A (lambda, tau) sweep yields a `sensitivity_band`; warnings flag "
        "effective_N < 2, single-paper evidence, and all-positive / "
        "all-negative observations."
    )
    lines.append("")
    lines.append(
        "**Pattern layer.** Per-pattern statistics use frequency, saturation "
        "index, and a freshness flag together with a predicted score that "
        "softly rewards fresh patterns and downweights saturated ones via "
        "novelty bias `alpha`. No credible interval is reported at the "
        "pattern level — per-cell evidence is too sparse (typically 0–5 hits "
        "across 11–28 papers) to support an honest CI. Wording at this layer "
        "is deliberately frequency + saturation + freshness, never 'posterior'."
    )
    lines.append("")
    lines.append("**Hyperparameters**")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    for key, value in sorted(hyperparameters.items()):
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append(
        "_References: `references/methodology.md`, "
        "`references/tier-definitions.md`._"
    )
    lines.append("")


__all__ = ("write_markdown",)
