"""Per-KP cheat-sheet assembly for the revision-plan DOCX writer.

The previous report writer produced wall-of-text statistical summaries with
no per-KP "how it will be tested" section. This module fixes that by
assembling deterministic, structured per-KP cards from the existing
pipeline outputs (KP posteriors + pattern coverage + pattern definitions +
mapping questions + tier narratives).

The module is pure and I/O-free. It does not generate prose; that is the
responsibility of the Opus `statistical-interpreter` subagent which emits
``tier-narratives.json``. This module only stitches deterministic structure.

The output schema mirrors the user's hand-curated reference docs:
    title, lecture/module ref, frequency tier, past-paper refs, narrative,
    drill bullets, dominant pattern, saturated/hot/fresh/dormant variants,
    already-tested examples, still-possible variants, open caveats.

Cross-cutting rules:
- Frozen dataclasses everywhere — callers must not mutate.
- Top-3 cap on tier-bucketed pattern variants, top-6 cap on already-tested
  examples, top-4 cap on still-possible.
- When ``patterns.json`` is missing (KP-only run), the sheet sets
  ``has_pattern_data = False`` and pattern-shaped fields are empty tuples.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .pattern_coverage import PatternCoverage, PatternOccurrence
from .statistical_model import KPPosterior


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_TOP_VARIANTS_PER_TIER: int = 3
_MAX_ALREADY_TESTED: int = 6
_MAX_STILL_POSSIBLE: int = 4
_FRACTION_JUN: float = 0.4
_FRACTION_OCT: float = 0.8
_TOLERANCE_FRACTION: float = 0.05

_CAVEAT_TOKENS: tuple[str, ...] = (
    "single-paper",
    "n_eff",
    "curriculum-only",
    "curriculum inference",
    "all-positive",
    "all-negative",
    "all observations positive",
    "all observations negative",
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheatSheetExample:
    """One past-paper instance of a (KP, pattern) cell."""

    year: float
    year_label: str
    question_number: str
    pattern_id: str
    pattern_label: str
    prompt_summary: str
    complications_used: tuple[str, ...]


@dataclass(frozen=True)
class CheatSheetVariant:
    """One pattern variant of a KP, with reasons + solution sketch."""

    pattern_id: str
    pattern_label: str
    rationale: str
    raw_hits: int
    weighted_hits: float
    saturation_index: float
    freshness_flag: bool
    pattern_tier: str
    solution_sketch: tuple[str, ...]
    common_complications_unseen: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class KPCheatSheet:
    """Structured per-KP card. The DOCX writer renders this into a card layout."""

    kp_id: str
    kp_label: str
    lecture_ref: str
    description: str
    tier: str
    tier_reasons: tuple[str, ...]
    posterior_summary: str
    headline: str
    narrative: str
    dominant_pattern: CheatSheetVariant | None
    saturated_patterns: tuple[CheatSheetVariant, ...]
    fresh_patterns: tuple[CheatSheetVariant, ...]
    hot_patterns: tuple[CheatSheetVariant, ...]
    dormant_patterns: tuple[CheatSheetVariant, ...]
    already_tested: tuple[CheatSheetExample, ...]
    still_possible: tuple[CheatSheetVariant, ...]
    drill_set: tuple[str, ...]
    past_paper_refs: tuple[str, ...]
    open_caveats: tuple[str, ...]
    has_pattern_data: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def year_to_label(year: float) -> str:
    """Convert a numeric year (Jan=.0, Jun=.4, Oct=.8) to '2024 Jun' style.

    Years are encoded with the fractional part marking the sitting:
    ``.0 -> Jan``, ``.4 -> Jun``, ``.8 -> Oct``. Anything within
    ``_TOLERANCE_FRACTION`` of those anchors snaps to the anchor; otherwise
    only the integer year is returned.
    """
    base = int(year)
    fraction = float(year) - base
    if abs(fraction) <= _TOLERANCE_FRACTION:
        return f"{base} Jan"
    if abs(fraction - _FRACTION_JUN) <= _TOLERANCE_FRACTION:
        return f"{base} Jun"
    if abs(fraction - _FRACTION_OCT) <= _TOLERANCE_FRACTION:
        return f"{base} Oct"
    return f"{base}"


def _format_posterior_summary(posterior: KPPosterior) -> str:
    """Render the posterior as a human-readable string.

    Uses the wording rules from references/methodology.md: when the KP has
    at least two papers behind it, expose the mean and the 95% CI. Otherwise
    fall back to a raw frequency since the CI is dominated by the prior.
    """
    if posterior.n_papers >= 2:
        return (
            f"{posterior.posterior_mean:.2f} "
            f"[{posterior.ci_lower_95:.2f}, {posterior.ci_upper_95:.2f}] "
            f"({posterior.tier})"
        )
    return f"frequency {posterior.raw_hits}/{posterior.n_papers} ({posterior.tier})"


def _derive_lecture_ref(kp_id: str, kp_record: dict | None) -> str:
    if kp_record:
        prefix = kp_record.get("lecture_prefix")
        if prefix:
            return str(prefix)
    if "." in kp_id:
        return kp_id.split(".", 1)[0]
    return kp_id


def _kp_label_from_record(kp_id: str, kp_record: dict | None) -> str:
    if not kp_record:
        return kp_id
    label = kp_record.get("label") or kp_record.get("title") or kp_record.get("name")
    return str(label) if label else kp_id


def _kp_description(kp_record: dict | None) -> str:
    if not kp_record:
        return ""
    description = kp_record.get("description") or ""
    return str(description)


def _index_patterns(pattern_definitions: list[dict]) -> dict[str, dict]:
    return {p["pattern_id"]: p for p in pattern_definitions if p.get("pattern_id")}


def _index_questions(mapping_questions: list[dict]) -> dict[tuple[float, str], dict]:
    """Index mapping questions by (year, question_number) for lookup."""
    indexed: dict[tuple[float, str], dict] = {}
    for question in mapping_questions:
        year = float(question.get("year", 0.0))
        qno = str(question.get("question_number", "?"))
        indexed[(year, qno)] = question
    return indexed


def _pattern_label(pattern: dict | None, pattern_id: str) -> str:
    if not pattern:
        return pattern_id
    label = pattern.get("label") or pattern_id
    return str(label)


def _solution_sketch(pattern: dict | None) -> tuple[str, ...]:
    if not pattern:
        return ()
    sketch = pattern.get("solution_sketch") or ()
    return tuple(str(step) for step in sketch)


def _sources(pattern: dict | None) -> tuple[str, ...]:
    if not pattern:
        return ()
    sources = pattern.get("source") or ()
    return tuple(str(s) for s in sources)


# ---------------------------------------------------------------------------
# Variant rationale strings
# ---------------------------------------------------------------------------


def _rationale_saturated(coverage: PatternCoverage) -> str:
    if coverage.last_seen_year is None:
        return "saturated: examiner has been recycling this pattern"
    last_label = year_to_label(coverage.last_seen_year)
    return (
        f"saturated: appeared {coverage.raw_hits}x "
        f"(last seen {last_label}); examiner has been recycling"
    )


def _rationale_hot(coverage: PatternCoverage) -> str:
    if (
        coverage.first_seen_year is not None
        and coverage.last_seen_year is not None
        and coverage.last_seen_year >= coverage.first_seen_year
    ):
        span = coverage.last_seen_year - coverage.first_seen_year
        span_str = f"{span:.1f}"
    else:
        span_str = "?"
    return f"hot: appeared {coverage.raw_hits}x across {span_str} years"


def _rationale_fresh(coverage: PatternCoverage, sources: tuple[str, ...]) -> str:
    first_source = sources[0] if sources else "material"
    if coverage.raw_hits == 0:
        return f"never tested; seeded by {first_source}"
    if coverage.last_seen_year is not None:
        gap_label = year_to_label(coverage.last_seen_year)
        return (
            f"fresh: seeded by {first_source} but not seen since {gap_label}"
        )
    return f"fresh: seeded by {first_source}"


def _rationale_dormant(coverage: PatternCoverage) -> str:
    if coverage.raw_hits == 0:
        return "dormant: not seen in available papers and not seeded as fresh"
    last_label = (
        year_to_label(coverage.last_seen_year)
        if coverage.last_seen_year is not None
        else "?"
    )
    return (
        f"recurrent but low-density: appeared {coverage.raw_hits}x "
        f"(last seen {last_label}); usable as a drill anchor when data is thin"
    )


def _rationale_for_tier(
    coverage: PatternCoverage,
    sources: tuple[str, ...],
) -> str:
    tier = coverage.tier
    if tier == "saturated":
        return _rationale_saturated(coverage)
    if tier == "hot":
        return _rationale_hot(coverage)
    if tier == "fresh":
        return _rationale_fresh(coverage, sources)
    if tier == "dormant":
        return _rationale_dormant(coverage)
    return f"{tier or 'untiered'}: see pattern statistics"


# ---------------------------------------------------------------------------
# Variant builders
# ---------------------------------------------------------------------------


def _build_variant(
    coverage: PatternCoverage,
    pattern: dict | None,
) -> CheatSheetVariant:
    label = _pattern_label(pattern, coverage.pattern_id)
    sketch = _solution_sketch(pattern)
    sources = _sources(pattern)
    rationale = _rationale_for_tier(coverage, sources)
    return CheatSheetVariant(
        pattern_id=coverage.pattern_id,
        pattern_label=label,
        rationale=rationale,
        raw_hits=coverage.raw_hits,
        weighted_hits=coverage.weighted_hits,
        saturation_index=coverage.saturation_index,
        freshness_flag=coverage.freshness_flag,
        pattern_tier=coverage.tier,
        solution_sketch=sketch,
        common_complications_unseen=coverage.complications_unseen,
        sources=sources,
    )


def _filter_and_cap(
    coverages: list[PatternCoverage],
    pattern_index: dict[str, dict],
    tier_name: str,
    cap: int,
) -> tuple[CheatSheetVariant, ...]:
    """Select coverages with a given tier, sorted by predicted_score desc, capped."""
    filtered = [c for c in coverages if c.tier == tier_name]
    filtered.sort(key=lambda c: c.predicted_score, reverse=True)
    capped = filtered[:cap]
    return tuple(
        _build_variant(c, pattern_index.get(c.pattern_id))
        for c in capped
    )


def _dominant_pattern(
    coverages: list[PatternCoverage],
    pattern_index: dict[str, dict],
) -> CheatSheetVariant | None:
    if not coverages:
        return None
    dominant = max(coverages, key=lambda c: c.predicted_score)
    return _build_variant(dominant, pattern_index.get(dominant.pattern_id))


# ---------------------------------------------------------------------------
# Already-tested + still-possible
# ---------------------------------------------------------------------------


def _build_already_tested(
    coverages: list[PatternCoverage],
    pattern_index: dict[str, dict],
    questions_by_yr_qno: dict[tuple[float, str], dict],
) -> tuple[CheatSheetExample, ...]:
    examples: list[CheatSheetExample] = []
    for coverage in coverages:
        pattern = pattern_index.get(coverage.pattern_id)
        label = _pattern_label(pattern, coverage.pattern_id)
        for occ in coverage.occurrences:
            question = questions_by_yr_qno.get((occ.year, occ.question_number)) or {}
            prompt_summary = str(question.get("prompt_summary", "") or "")
            examples.append(
                CheatSheetExample(
                    year=occ.year,
                    year_label=year_to_label(occ.year),
                    question_number=occ.question_number,
                    pattern_id=coverage.pattern_id,
                    pattern_label=label,
                    prompt_summary=prompt_summary,
                    complications_used=tuple(occ.complications),
                )
            )
    examples.sort(key=lambda e: e.year, reverse=True)
    return tuple(examples[:_MAX_ALREADY_TESTED])


def _build_still_possible(
    coverages: list[PatternCoverage],
    pattern_index: dict[str, dict],
) -> tuple[CheatSheetVariant, ...]:
    """Fresh patterns + saturated patterns with unseen complications.

    Sort: fresh first (by predicted_score desc), then saturated-with-unseen
    (also predicted_score desc). Capped at _MAX_STILL_POSSIBLE.
    """
    fresh = [c for c in coverages if c.freshness_flag]
    saturated_with_unseen = [
        c
        for c in coverages
        if c.tier == "saturated" and c.complications_unseen and not c.freshness_flag
    ]
    fresh.sort(key=lambda c: c.predicted_score, reverse=True)
    saturated_with_unseen.sort(key=lambda c: c.predicted_score, reverse=True)
    ordered = fresh + saturated_with_unseen
    capped = ordered[:_MAX_STILL_POSSIBLE]
    return tuple(
        _build_variant(c, pattern_index.get(c.pattern_id))
        for c in capped
    )


# ---------------------------------------------------------------------------
# Past-paper references + caveats + headline + drill set
# ---------------------------------------------------------------------------


def _past_paper_refs(already_tested: tuple[CheatSheetExample, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    refs: list[str] = []
    for example in already_tested:
        ref = f"{example.year_label} Q{example.question_number}"
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return tuple(refs)


def _open_caveats(
    posterior: KPPosterior,
    tier_reasons: tuple[str, ...],
) -> tuple[str, ...]:
    caveats: list[str] = list(posterior.warnings)
    for reason in tier_reasons:
        lowered = reason.lower()
        for token in _CAVEAT_TOKENS:
            if token in lowered and reason not in caveats:
                caveats.append(reason)
                break
    return tuple(caveats)


def _headline_fallback(
    posterior: KPPosterior,
    dominant: CheatSheetVariant | None,
) -> str:
    if dominant is not None:
        return (
            f"Tier {posterior.tier}: posterior {posterior.posterior_mean:.2f}, "
            f"dominant pattern {dominant.pattern_id}."
        )
    return f"Tier {posterior.tier}: posterior {posterior.posterior_mean:.2f}."


def _narrative_drill_set(narrative: dict | None) -> tuple[str, ...] | None:
    if not narrative:
        return None
    drill = narrative.get("drill_set")
    if not drill:
        return None
    return tuple(str(item) for item in drill)


def _drill_set_fallback(
    already_tested: tuple[CheatSheetExample, ...],
    dominant: CheatSheetVariant | None,
    fresh_variants: tuple[CheatSheetVariant, ...],
) -> tuple[str, ...]:
    bullets: list[str] = []
    if already_tested:
        most_recent = already_tested[0]
        bullets.append(
            f"{most_recent.year_label} Q{most_recent.question_number} "
            f"({most_recent.pattern_id}) — most recent past-paper hit"
        )
    if dominant is not None and dominant.solution_sketch:
        bullets.append(
            f"Dominant {dominant.pattern_id}: {dominant.solution_sketch[0]}"
        )
    if fresh_variants:
        first_fresh = fresh_variants[0]
        if first_fresh.solution_sketch:
            bullets.append(
                f"Fresh {first_fresh.pattern_id}: {first_fresh.solution_sketch[0]}"
            )
    return tuple(bullets)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_kp_cheatsheet(
    posterior: KPPosterior,
    pattern_coverages: list[PatternCoverage],
    pattern_definitions: list[dict],
    mapping_questions: list[dict],
    kp_record: dict | None,
    narrative: dict | None,
) -> KPCheatSheet:
    """Build the structured cheat-sheet for one KP.

    Pure function. No I/O. When ``pattern_definitions`` is empty, returns a
    KP-only sheet with ``has_pattern_data = False`` and empty pattern
    fields.
    """
    has_pattern_data = bool(pattern_definitions)
    pattern_index = _index_patterns(pattern_definitions)
    questions_by_yr_qno = _index_questions(mapping_questions)

    if has_pattern_data:
        dominant = _dominant_pattern(pattern_coverages, pattern_index)
        saturated = _filter_and_cap(
            pattern_coverages, pattern_index, "saturated", _TOP_VARIANTS_PER_TIER
        )
        hot = _filter_and_cap(
            pattern_coverages, pattern_index, "hot", _TOP_VARIANTS_PER_TIER
        )
        fresh = _filter_and_cap(
            pattern_coverages, pattern_index, "fresh", _TOP_VARIANTS_PER_TIER
        )
        dormant = _filter_and_cap(
            pattern_coverages, pattern_index, "dormant", _TOP_VARIANTS_PER_TIER
        )
        already_tested = _build_already_tested(
            pattern_coverages, pattern_index, questions_by_yr_qno
        )
        still_possible = _build_still_possible(pattern_coverages, pattern_index)
    else:
        dominant = None
        saturated = ()
        hot = ()
        fresh = ()
        dormant = ()
        already_tested = ()
        still_possible = ()

    past_paper_refs = _past_paper_refs(already_tested)
    open_caveats = _open_caveats(posterior, posterior.tier_reasons)

    narrative_headline = (
        str(narrative.get("headline", "")).strip() if narrative else ""
    )
    headline = narrative_headline or _headline_fallback(posterior, dominant)

    narrative_text = (
        str(narrative.get("narrative", "")).strip() if narrative else ""
    )

    drill_from_narrative = _narrative_drill_set(narrative)
    if drill_from_narrative:
        drill_set = drill_from_narrative
    else:
        drill_set = _drill_set_fallback(already_tested, dominant, fresh)

    return KPCheatSheet(
        kp_id=posterior.kp_id,
        kp_label=_kp_label_from_record(posterior.kp_id, kp_record),
        lecture_ref=_derive_lecture_ref(posterior.kp_id, kp_record),
        description=_kp_description(kp_record),
        tier=posterior.tier,
        tier_reasons=tuple(posterior.tier_reasons),
        posterior_summary=_format_posterior_summary(posterior),
        headline=headline,
        narrative=narrative_text,
        dominant_pattern=dominant,
        saturated_patterns=saturated,
        fresh_patterns=fresh,
        hot_patterns=hot,
        dormant_patterns=dormant,
        already_tested=already_tested,
        still_possible=still_possible,
        drill_set=drill_set,
        past_paper_refs=past_paper_refs,
        open_caveats=open_caveats,
        has_pattern_data=has_pattern_data,
    )


def _patterns_by_kp(pattern_definitions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for pattern in pattern_definitions:
        kp_id = pattern.get("kp_id")
        if not kp_id:
            continue
        grouped.setdefault(kp_id, []).append(pattern)
    return grouped


def _coverages_by_kp(coverages: list[PatternCoverage]) -> dict[str, list[PatternCoverage]]:
    grouped: dict[str, list[PatternCoverage]] = {}
    for coverage in coverages:
        grouped.setdefault(coverage.kp_id, []).append(coverage)
    return grouped


def _questions_by_kp(mapping_questions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for question in mapping_questions:
        primary = question.get("primary_kp")
        if not primary:
            continue
        grouped.setdefault(primary, []).append(question)
    return grouped


def _kps_by_id(kps: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for record in kps:
        kp_id = record.get("kp_id") or record.get("id")
        if not kp_id:
            continue
        indexed[str(kp_id)] = record
    return indexed


def build_all_cheatsheets(
    posteriors: list[KPPosterior],
    pattern_coverages: list[PatternCoverage],
    pattern_definitions: list[dict],
    mapping_questions: list[dict],
    kps: list[dict],
    narratives: dict[str, dict] | None,
) -> dict[str, KPCheatSheet]:
    """Build one ``KPCheatSheet`` per posterior, keyed by ``kp_id``.

    Pure function. Groups the input lists by KP once so each per-KP build
    is O(patterns_for_that_kp + questions_for_that_kp).
    """
    patterns_grouped = _patterns_by_kp(pattern_definitions)
    coverages_grouped = _coverages_by_kp(pattern_coverages)
    questions_grouped = _questions_by_kp(mapping_questions)
    kp_index = _kps_by_id(kps)
    narratives_safe = narratives or {}

    sheets: dict[str, KPCheatSheet] = {}
    for posterior in posteriors:
        kp_id = posterior.kp_id
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages_grouped.get(kp_id, []),
            pattern_definitions=patterns_grouped.get(kp_id, []),
            mapping_questions=questions_grouped.get(kp_id, []),
            kp_record=kp_index.get(kp_id),
            narrative=narratives_safe.get(kp_id),
        )
        sheets[kp_id] = sheet
    return sheets


__all__ = (
    "CheatSheetExample",
    "CheatSheetVariant",
    "KPCheatSheet",
    "build_all_cheatsheets",
    "build_kp_cheatsheet",
    "year_to_label",
)
