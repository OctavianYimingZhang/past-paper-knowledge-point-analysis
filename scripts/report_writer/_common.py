"""Shared constants, types, and helpers for the report writers.

The report writer is split across:

- ``__init__.py`` — the public API plus the Excel/JSON writers (which were
  unchanged in the new layout).
- ``_docx.py`` — the DOCX writer with executive summary, per-KP cheat-sheets,
  sensitivity, and appendices.
- ``_markdown.py`` — the Markdown writer that mirrors the same section order.
- ``_common.py`` (this file) — shared constants, type aliases, the
  cheat-sheet builder bridge, summary derivations (``_top_focus_kps``,
  ``_caveat_bullets`` etc.), and tiny helpers.
"""
from __future__ import annotations

import json
from typing import Literal

from ..kp_cheatsheet import (
    CheatSheetExample,
    CheatSheetVariant,
    KPCheatSheet,
    build_all_cheatsheets,
)
from ..pattern_coverage import PatternCoverage
from ..statistical_model import KPPosterior


ReportLang = Literal["en", "zh", "both"]


# ---------------------------------------------------------------------------
# Tier ordering / titles
# ---------------------------------------------------------------------------


TIER_ORDER: tuple[str, ...] = (
    "anchor",
    "core",
    "emerging",
    "legacy",
    "oneoff",
    "not_tested",
)

TIER_TITLES_EN: dict[str, str] = {
    "anchor": "Anchor",
    "core": "Core",
    "emerging": "Emerging",
    "legacy": "Legacy",
    "oneoff": "One-off",
    "not_tested": "Not tested",
}

TIER_TITLES_ZH: dict[str, str] = {
    "anchor": "锚点",
    "core": "核心",
    "emerging": "上升题",
    "legacy": "退潮题",
    "oneoff": "偶现题",
    "not_tested": "未考查",
}


# Caps for the various summary blocks.
TOP_KP_SUMMARY_CAP: int = 5
TOP_FRESH_SUMMARY_CAP: int = 5
MAX_CAVEAT_BULLETS: int = 3
MAX_ALREADY_TESTED_ROWS: int = 6
MAX_STILL_POSSIBLE_ROWS: int = 4


# Heading strings — kept stable so tests can locate them.
SECTION_EXEC_SUMMARY: str = "Executive Summary"
SECTION_PREDICTIONS: str = "KP Predictions"
SECTION_CHEAT_SHEETS: str = "How It Will Be Tested"
SECTION_SENSITIVITY: str = "Sensitivity & Warnings"
APPENDIX_AUDIT: str = "Appendix A — Full KP Audit Table"
APPENDIX_PATTERNS: str = "Appendix B — Pattern Catalogue"
APPENDIX_METHODOLOGY: str = "Appendix C — Methodology"


# ---------------------------------------------------------------------------
# Translation + scalar helpers
# ---------------------------------------------------------------------------


def render_text(en: str, zh: str, lang: ReportLang) -> str:
    """Render text in the requested language."""
    if lang == "en":
        return en
    if lang == "zh":
        return zh
    return f"{en}\n{zh}"


def scalar_str(value: object) -> str:
    """Coerce non-primitive values into a one-line string for tables."""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


# ---------------------------------------------------------------------------
# Confidence chip + table sort orders
# ---------------------------------------------------------------------------


def confidence_chip(posterior: KPPosterior) -> str:
    """Reduce posterior numbers to a coarse high/medium/low chip."""
    if posterior.ci_lower_95 >= 0.50:
        return "high"
    if posterior.posterior_mean >= 0.40:
        return "medium"
    return "low"


def confidence_chip_zh(chip: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(chip, chip)


def sort_for_predictions_table(posteriors: list[KPPosterior]) -> list[KPPosterior]:
    """Sort by tier (TIER_ORDER), then posterior_mean descending."""
    tier_index = {t: i for i, t in enumerate(TIER_ORDER)}
    return sorted(
        posteriors,
        key=lambda p: (
            tier_index.get(p.tier, len(TIER_ORDER)),
            -p.posterior_mean,
            p.kp_id,
        ),
    )


# ---------------------------------------------------------------------------
# Executive summary derivations
# ---------------------------------------------------------------------------


def top_focus_kps(
    posteriors: list[KPPosterior],
    sheets: dict[str, KPCheatSheet] | None,
    cap: int = TOP_KP_SUMMARY_CAP,
) -> list[tuple[KPPosterior, KPCheatSheet | None]]:
    """Top KPs sorted by posterior mean.

    Prefers anchor + core. When the data is too thin for any KP to clear
    those tiers (e.g. only one paper available), falls back to including
    ``emerging`` and ``oneoff`` KPs so the cheat-sheet section is never
    empty for a course with at least one mapped question.
    """
    primary = [p for p in posteriors if p.tier in ("anchor", "core")]
    primary.sort(key=lambda p: (-p.posterior_mean, p.kp_id))
    if primary:
        focus = primary
    else:
        fallback_tiers = ("emerging", "oneoff", "legacy")
        fallback = [p for p in posteriors if p.tier in fallback_tiers]
        fallback.sort(key=lambda p: (-p.posterior_mean, p.kp_id))
        focus = fallback
    out: list[tuple[KPPosterior, KPCheatSheet | None]] = []
    for posterior in focus[:cap]:
        sheet = sheets.get(posterior.kp_id) if sheets else None
        out.append((posterior, sheet))
    return out


def top_fresh_targets(
    sheets: dict[str, KPCheatSheet] | None,
    cap: int = TOP_FRESH_SUMMARY_CAP,
) -> list[tuple[KPCheatSheet, CheatSheetVariant]]:
    """Highest-priority fresh patterns, capped."""
    if not sheets:
        return []
    candidates: list[tuple[KPCheatSheet, CheatSheetVariant]] = []
    for sheet in sheets.values():
        for variant in sheet.fresh_patterns:
            candidates.append((sheet, variant))
    # Surface sourced fresh patterns first, then richer source lists, then
    # alphabetical for determinism.
    candidates.sort(
        key=lambda item: (
            0 if item[1].sources else 1,
            -len(item[1].sources),
            item[0].kp_id,
            item[1].pattern_id,
        )
    )
    return candidates[:cap]


def caveat_bullets(
    posteriors: list[KPPosterior],
    cap: int = MAX_CAVEAT_BULLETS,
) -> list[str]:
    """Compose <= cap short caveat bullets."""
    bullets: list[str] = []
    unstable = [p for p in posteriors if p.sensitivity_band == "unstable"]
    if unstable:
        ids = ", ".join(p.kp_id for p in unstable[:5])
        bullets.append(
            f"{len(unstable)} KP(s) flipped tiers across the (lambda, tau) sweep: {ids}."
        )
    n_eff_warned = [
        p for p in posteriors if any("effective_N" in w for w in p.warnings)
    ]
    if n_eff_warned:
        ids = ", ".join(p.kp_id for p in n_eff_warned[:5])
        bullets.append(
            f"{len(n_eff_warned)} KP(s) have effective_N < 2 (prior-dominated): {ids}."
        )
    single_paper = [p for p in posteriors if p.n_papers <= 1]
    if single_paper:
        ids = ", ".join(p.kp_id for p in single_paper[:5])
        bullets.append(
            f"{len(single_paper)} KP(s) rest on a single paper of evidence: {ids}."
        )
    return bullets[:cap]


def executive_headline(
    posteriors: list[KPPosterior],
    course_meta: dict,
    sheets: dict[str, KPCheatSheet] | None,
) -> str:
    """Generate a 3-4 sentence headline from the data."""
    n_kp = len(posteriors)
    n_anchor = sum(1 for p in posteriors if p.tier == "anchor")
    n_core = sum(1 for p in posteriors if p.tier == "core")
    n_unstable = sum(1 for p in posteriors if p.sensitivity_band == "unstable")
    n_fresh = 0
    if sheets:
        n_fresh = sum(len(s.fresh_patterns) for s in sheets.values())

    course_name = course_meta.get("course_name", "the course")
    reference_year = course_meta.get("reference_year", "?")
    n_papers = course_meta.get("n_papers", "?")

    sentences: list[str] = []
    sentences.append(
        f"This run covers {n_kp} knowledge points for {course_name} with "
        f"reference year {reference_year} across {n_papers} formal paper(s)."
    )
    sentences.append(
        f"The model identifies {n_anchor} anchor and {n_core} core KP(s), "
        f"which together set the bulk of revision priority."
    )
    if n_fresh:
        sentences.append(
            f"The pattern layer flags {n_fresh} fresh pattern(s) seeded by "
            "course material but not used recently — asymmetric upside if drilled."
        )
    else:
        sentences.append(
            "No pattern layer was supplied for this run, so cheat-sheets fall back "
            "to KP-level commentary only."
        )
    if n_unstable:
        sentences.append(
            f"Treat {n_unstable} unstable KP(s) with caution: their tier flipped "
            "across the (lambda, tau) sweep — see the Sensitivity section."
        )
    else:
        sentences.append(
            "Tier assignments are robust across the (lambda, tau) sensitivity sweep."
        )
    return " ".join(sentences)


# ---------------------------------------------------------------------------
# Sheet bridge + course-meta merge + label index
# ---------------------------------------------------------------------------


def label_index(pattern_definitions: list[dict] | None) -> dict[str, str]:
    if not pattern_definitions:
        return {}
    return {
        str(p["pattern_id"]): str(p.get("label", ""))
        for p in pattern_definitions
        if p.get("pattern_id")
    }


def build_sheets(
    posteriors: list[KPPosterior],
    pattern_coverage: list[PatternCoverage] | None,
    pattern_definitions: list[dict] | None,
    mapping_questions: list[dict] | None,
    kps: list[dict] | None,
    tier_narratives: dict | None,
) -> dict[str, KPCheatSheet] | None:
    """Build the per-KP cheat-sheet map, or None if no pattern layer exists."""
    if pattern_coverage is None and pattern_definitions is None:
        return None
    return build_all_cheatsheets(
        posteriors=posteriors,
        pattern_coverages=list(pattern_coverage or []),
        pattern_definitions=list(pattern_definitions or []),
        mapping_questions=list(mapping_questions or []),
        kps=list(kps or []),
        narratives=dict(tier_narratives or {}),
    )


def resolve_course_meta(
    course_meta: dict | None,
    hyperparameters: dict,
    posteriors: list[KPPosterior],
) -> dict:
    """Merge an explicit course_meta dict with hyperparameters fallbacks."""
    merged = {
        "course_id": hyperparameters.get("course_id", "course"),
        "course_name": hyperparameters.get("course_name", "Past-Paper Analysis"),
        "reference_year": hyperparameters.get("reference_year", "?"),
        "n_papers": hyperparameters.get("n_papers", "?"),
        "n_kps": hyperparameters.get("n_kp", len(posteriors)),
    }
    if course_meta:
        for k, v in course_meta.items():
            if v is not None:
                merged[k] = v
    return merged


__all__ = (
    "APPENDIX_AUDIT",
    "APPENDIX_METHODOLOGY",
    "APPENDIX_PATTERNS",
    "CheatSheetExample",
    "CheatSheetVariant",
    "KPCheatSheet",
    "MAX_ALREADY_TESTED_ROWS",
    "MAX_CAVEAT_BULLETS",
    "MAX_STILL_POSSIBLE_ROWS",
    "PatternCoverage",
    "ReportLang",
    "SECTION_CHEAT_SHEETS",
    "SECTION_EXEC_SUMMARY",
    "SECTION_PREDICTIONS",
    "SECTION_SENSITIVITY",
    "TIER_ORDER",
    "TIER_TITLES_EN",
    "TIER_TITLES_ZH",
    "TOP_FRESH_SUMMARY_CAP",
    "TOP_KP_SUMMARY_CAP",
    "build_sheets",
    "caveat_bullets",
    "confidence_chip",
    "confidence_chip_zh",
    "executive_headline",
    "label_index",
    "render_text",
    "resolve_course_meta",
    "scalar_str",
    "sort_for_predictions_table",
    "top_focus_kps",
    "top_fresh_targets",
)
