"""Unit tests for the per-KP cheat-sheet assembler.

The cheat-sheet module is pure structure — it stitches deterministic data
from `KPPosterior`, `PatternCoverage`, the patterns.json definitions, the
mapping.json questions, and the optional Opus narratives. These tests
exercise the contract the DOCX writer relies on:

* KP-only runs (no patterns.json) yield empty pattern fields.
* Dominant pattern is the highest-predicted_score row.
* tier-bucketed pattern lists filter and cap correctly.
* Already-tested examples sort year-descending and cap at six.
* Still-possible includes fresh + saturated-with-unseen-complications.
* Posterior summary formatting tracks the methodology rules.
* Lecture ref is taken from kp_record when present.
* Drill set prefers narrative when present, else the deterministic combo.
* Year encoding maps .0/.4/.8 to Jan/Jun/Oct.
* Caveats merge posterior warnings with curriculum-only / single-paper
  tier reasons.
* `build_all_cheatsheets` produces one entry per posterior.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.kp_cheatsheet import (
    CheatSheetExample,
    CheatSheetVariant,
    KPCheatSheet,
    build_all_cheatsheets,
    build_kp_cheatsheet,
    year_to_label,
)
from scripts.pattern_coverage import PatternCoverage, PatternOccurrence
from scripts.statistical_model import KPPosterior


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_posterior(
    kp_id: str = "L13.03",
    tier: str = "anchor",
    posterior_mean: float = 0.82,
    ci_lower_95: float = 0.42,
    ci_upper_95: float = 1.00,
    n_papers: int = 8,
    raw_hits: int = 6,
    tier_reasons: tuple[str, ...] = ("posterior_mean=0.82 >= 0.75",),
    warnings: tuple[str, ...] = (),
) -> KPPosterior:
    return KPPosterior(
        kp_id=kp_id,
        n_papers=n_papers,
        raw_hits=raw_hits,
        weighted_hits=float(raw_hits),
        weighted_N=float(n_papers),
        lambda_used=0.2,
        tau_used=1.0,
        reference_year=2026,
        coverage_share=0.1,
        prior_alpha=0.1,
        prior_beta=0.9,
        posterior_alpha=6.1,
        posterior_beta=2.9,
        posterior_mean=posterior_mean,
        ci_lower_95=ci_lower_95,
        ci_upper_95=ci_upper_95,
        hotness_mean_share=0.1,
        hotness_std_share=0.02,
        trend_label="stable",
        trend_delta=0.0,
        trend_ci_95=(-0.1, 0.1),
        historical_mean=raw_hits / n_papers if n_papers else 0.0,
        tier=tier,
        tier_reasons=tier_reasons,
        sensitivity_band="stable",
        warnings=warnings,
    )


def make_coverage(
    kp_id: str = "L13.03",
    pattern_id: str = "L13.03.P02",
    raw_hits: int = 0,
    weighted_hits: float = 0.0,
    last_seen_year: float | None = None,
    first_seen_year: float | None = None,
    saturation_index: float = 0.0,
    freshness_flag: bool = False,
    predicted_score: float = 0.0,
    complications_seen: tuple[str, ...] = (),
    complications_unseen: tuple[str, ...] = (),
    occurrences: tuple[PatternOccurrence, ...] = (),
    tier: str = "dormant",
) -> PatternCoverage:
    return PatternCoverage(
        kp_id=kp_id,
        pattern_id=pattern_id,
        raw_hits=raw_hits,
        weighted_hits=weighted_hits,
        last_seen_year=last_seen_year,
        first_seen_year=first_seen_year,
        inter_arrival_years_mean=None,
        inter_arrival_years_max=None,
        saturation_index=saturation_index,
        freshness_flag=freshness_flag,
        predicted_score=predicted_score,
        complications_seen=complications_seen,
        complications_unseen=complications_unseen,
        occurrences=occurrences,
        warnings=(),
        tier=tier,
        tier_reasons=(f"tier={tier}",),
    )


def make_occurrence(
    year: float,
    qno: str = "5",
    is_primary: bool = True,
    confidence: float = 1.0,
    complications: tuple[str, ...] = (),
) -> PatternOccurrence:
    return PatternOccurrence(
        year=year,
        question_number=qno,
        confidence=confidence,
        is_primary=is_primary,
        complications=complications,
    )


def make_pattern(
    pattern_id: str,
    kp_id: str = "L13.03",
    label: str = "Test pattern",
    sketch: tuple[str, ...] = ("step 1", "step 2"),
    sources: tuple[str, ...] = ("textbook §5.4 example 12",),
    common_complications: tuple[str, ...] = (),
) -> dict:
    return {
        "kp_id": kp_id,
        "pattern_id": pattern_id,
        "label": label,
        "solution_sketch": list(sketch),
        "source": list(sources),
        "common_complications": list(common_complications),
    }


def make_question(
    year: float,
    qno: str = "5",
    primary_kp: str = "L13.03",
    pattern_id: str = "L13.03.P02",
    prompt_summary: str = "Find tangent at the named point.",
) -> dict:
    return {
        "year": year,
        "question_number": qno,
        "primary_kp": primary_kp,
        "pattern_id": pattern_id,
        "prompt_summary": prompt_summary,
        "complications": [],
    }


# ---------------------------------------------------------------------------
# year_to_label
# ---------------------------------------------------------------------------


class TestYearLabel:
    def test_january_label(self):
        assert year_to_label(2024.0) == "2024 Jan"

    def test_june_label(self):
        assert year_to_label(2024.4) == "2024 Jun"

    def test_october_label(self):
        assert year_to_label(2024.8) == "2024 Oct"

    def test_integer_year_treated_as_january(self):
        assert year_to_label(2024) == "2024 Jan"

    def test_unknown_fraction_returns_year_only(self):
        assert year_to_label(2024.25) == "2024"


# ---------------------------------------------------------------------------
# KP-only / no patterns
# ---------------------------------------------------------------------------


class TestKPOnly:
    def test_no_pattern_layer_returns_empty_pattern_fields(self):
        posterior = make_posterior(
            kp_id="L13.03",
            tier="core",
            posterior_mean=0.55,
            ci_lower_95=0.30,
            ci_upper_95=0.80,
            n_papers=6,
            raw_hits=3,
        )
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert sheet.has_pattern_data is False
        assert sheet.dominant_pattern is None
        assert sheet.saturated_patterns == ()
        assert sheet.hot_patterns == ()
        assert sheet.fresh_patterns == ()
        assert sheet.dormant_patterns == ()
        assert sheet.already_tested == ()
        assert sheet.still_possible == ()
        # Posterior summary uses the mean + CI when n_papers >= 2.
        assert sheet.posterior_summary == "0.55 [0.30, 0.80] (core)"
        # Headline fallback omits pattern when none exists.
        assert "core" in sheet.headline.lower() or "Tier core" in sheet.headline


# ---------------------------------------------------------------------------
# Dominant pattern
# ---------------------------------------------------------------------------


class TestDominantPattern:
    def test_dominant_picks_highest_predicted_score(self):
        posterior = make_posterior()
        coverages = [
            make_coverage(pattern_id="L13.03.P01", predicted_score=0.20, tier="dormant"),
            make_coverage(pattern_id="L13.03.P02", predicted_score=0.85, tier="hot"),
            make_coverage(pattern_id="L13.03.P03", predicted_score=0.40, tier="fresh", freshness_flag=True),
            make_coverage(pattern_id="L13.03.P04", predicted_score=0.10, tier="dormant"),
        ]
        patterns = [
            make_pattern("L13.03.P01"),
            make_pattern("L13.03.P02"),
            make_pattern("L13.03.P03"),
            make_pattern("L13.03.P04"),
        ]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert sheet.has_pattern_data is True
        assert sheet.dominant_pattern is not None
        assert sheet.dominant_pattern.pattern_id == "L13.03.P02"


# ---------------------------------------------------------------------------
# Tier filtering and capping
# ---------------------------------------------------------------------------


class TestTierBuckets:
    def test_tier_lists_filter_correctly(self):
        posterior = make_posterior()
        coverages = [
            make_coverage(
                pattern_id="L13.03.P01",
                tier="saturated",
                predicted_score=0.9,
                raw_hits=3,
                last_seen_year=2025.4,
            ),
            make_coverage(pattern_id="L13.03.P02", tier="hot", predicted_score=0.6, raw_hits=2),
            make_coverage(
                pattern_id="L13.03.P03",
                tier="fresh",
                predicted_score=0.3,
                freshness_flag=True,
            ),
            make_coverage(pattern_id="L13.03.P04", tier="dormant", predicted_score=0.05),
        ]
        patterns = [make_pattern(c.pattern_id) for c in coverages]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert [v.pattern_id for v in sheet.saturated_patterns] == ["L13.03.P01"]
        assert [v.pattern_id for v in sheet.hot_patterns] == ["L13.03.P02"]
        assert [v.pattern_id for v in sheet.fresh_patterns] == ["L13.03.P03"]
        assert [v.pattern_id for v in sheet.dormant_patterns] == ["L13.03.P04"]

    def test_tier_lists_capped_at_three(self):
        posterior = make_posterior()
        # Five fresh patterns; only the top 3 by predicted_score survive.
        coverages = [
            make_coverage(
                pattern_id=f"L13.03.P0{idx}",
                tier="fresh",
                predicted_score=float(idx) / 10.0,
                freshness_flag=True,
            )
            for idx in range(1, 6)
        ]
        patterns = [make_pattern(c.pattern_id) for c in coverages]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert len(sheet.fresh_patterns) == 3
        assert [v.pattern_id for v in sheet.fresh_patterns] == [
            "L13.03.P05",
            "L13.03.P04",
            "L13.03.P03",
        ]


# ---------------------------------------------------------------------------
# Still-possible
# ---------------------------------------------------------------------------


class TestStillPossible:
    def test_includes_fresh_and_saturated_with_unseen_capped_at_four(self):
        posterior = make_posterior()
        coverages = [
            # Fresh — first by ordering rule.
            make_coverage(
                pattern_id="L13.03.P01",
                tier="fresh",
                freshness_flag=True,
                predicted_score=0.9,
            ),
            make_coverage(
                pattern_id="L13.03.P02",
                tier="fresh",
                freshness_flag=True,
                predicted_score=0.6,
            ),
            # Saturated WITH unseen complications — appears after fresh.
            make_coverage(
                pattern_id="L13.03.P03",
                tier="saturated",
                predicted_score=0.7,
                raw_hits=3,
                last_seen_year=2025.4,
                complications_unseen=("vertical-tangent edge case",),
            ),
            make_coverage(
                pattern_id="L13.03.P04",
                tier="saturated",
                predicted_score=0.5,
                raw_hits=3,
                last_seen_year=2024.4,
                complications_unseen=("indirect gradient",),
            ),
            # Saturated WITHOUT unseen — excluded.
            make_coverage(
                pattern_id="L13.03.P05",
                tier="saturated",
                predicted_score=0.8,
                raw_hits=3,
                last_seen_year=2025.4,
                complications_unseen=(),
            ),
            # Hot — excluded entirely.
            make_coverage(
                pattern_id="L13.03.P06",
                tier="hot",
                predicted_score=0.7,
                raw_hits=2,
            ),
        ]
        patterns = [make_pattern(c.pattern_id) for c in coverages]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        ids = [v.pattern_id for v in sheet.still_possible]
        # Fresh first (P01 score 0.9 then P02 score 0.6), then saturated-with-unseen
        # (P03 score 0.7 then P04 score 0.5). Hot (P06) and saturated-no-unseen
        # (P05) are excluded.
        assert ids == ["L13.03.P01", "L13.03.P02", "L13.03.P03", "L13.03.P04"]
        assert "L13.03.P05" not in ids
        assert "L13.03.P06" not in ids

    def test_still_possible_capped_at_four(self):
        posterior = make_posterior()
        coverages = [
            make_coverage(
                pattern_id=f"L13.03.P0{idx}",
                tier="fresh",
                freshness_flag=True,
                predicted_score=float(idx) / 10.0,
            )
            for idx in range(1, 7)
        ]
        patterns = [make_pattern(c.pattern_id) for c in coverages]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert len(sheet.still_possible) == 4


# ---------------------------------------------------------------------------
# Already-tested
# ---------------------------------------------------------------------------


class TestAlreadyTested:
    def test_sorted_year_descending_capped_at_six(self):
        posterior = make_posterior()
        # Single pattern with seven occurrences across different years.
        years = [2018.4, 2019.4, 2020.4, 2021.4, 2022.4, 2023.4, 2024.4]
        occurrences = tuple(make_occurrence(y, qno=str(i + 1)) for i, y in enumerate(years))
        coverage = make_coverage(
            pattern_id="L13.03.P01",
            tier="hot",
            predicted_score=0.7,
            raw_hits=len(occurrences),
            last_seen_year=2024.4,
            first_seen_year=2018.4,
            occurrences=occurrences,
        )
        patterns = [make_pattern("L13.03.P01")]
        questions = [
            make_question(year=y, qno=str(i + 1)) for i, y in enumerate(years)
        ]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[coverage],
            pattern_definitions=patterns,
            mapping_questions=questions,
            kp_record=None,
            narrative=None,
        )
        assert len(sheet.already_tested) == 6
        seen_years = [ex.year for ex in sheet.already_tested]
        assert seen_years == sorted(seen_years, reverse=True)
        assert sheet.already_tested[0].year == 2024.4
        # past_paper_refs reflect the same ordering.
        assert sheet.past_paper_refs[0] == "2024 Jun Q7"


# ---------------------------------------------------------------------------
# Posterior summary formatting
# ---------------------------------------------------------------------------


class TestPosteriorSummary:
    def test_one_paper_falls_back_to_frequency_string(self):
        posterior = make_posterior(
            kp_id="L01.01",
            tier="oneoff",
            n_papers=1,
            raw_hits=1,
            tier_reasons=("raw_hits=1 and no stronger signal",),
        )
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert sheet.posterior_summary == "frequency 1/1 (oneoff)"

    def test_multi_paper_uses_mean_and_ci(self):
        posterior = make_posterior(
            tier="anchor",
            posterior_mean=0.82,
            ci_lower_95=0.42,
            ci_upper_95=1.00,
        )
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert sheet.posterior_summary == "0.82 [0.42, 1.00] (anchor)"


# ---------------------------------------------------------------------------
# Lecture ref
# ---------------------------------------------------------------------------


class TestLectureRef:
    def test_lecture_prefix_from_kp_record_used_when_present(self):
        posterior = make_posterior(kp_id="L13.03")
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record={"kp_id": "L13.03", "lecture_prefix": "Lecture 14"},
            narrative=None,
        )
        assert sheet.lecture_ref == "Lecture 14"

    def test_fallback_uses_prefix_before_first_dot(self):
        posterior = make_posterior(kp_id="L13.03")
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert sheet.lecture_ref == "L13"


# ---------------------------------------------------------------------------
# Drill set
# ---------------------------------------------------------------------------


class TestDrillSet:
    def test_drill_set_uses_narrative_when_present(self):
        posterior = make_posterior()
        bullets = (
            "2023 Jan Q7 — same pattern, recent",
            "Textbook §5.4 example 12 — canonical setup",
            "Textbook §5.4 example 14 — vertical-tangent edge case",
        )
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative={"drill_set": list(bullets), "headline": "anchor narrative"},
        )
        assert sheet.drill_set == bullets

    def test_drill_set_fallback_combines_recent_dominant_fresh(self):
        posterior = make_posterior()
        coverages = [
            make_coverage(
                pattern_id="L13.03.P01",
                tier="hot",
                predicted_score=0.9,
                raw_hits=2,
                last_seen_year=2024.4,
                first_seen_year=2020.0,
                occurrences=(make_occurrence(2024.4, qno="7"),),
            ),
            make_coverage(
                pattern_id="L13.03.P02",
                tier="fresh",
                predicted_score=0.4,
                freshness_flag=True,
            ),
        ]
        patterns = [
            make_pattern("L13.03.P01", sketch=("differentiate", "substitute")),
            make_pattern("L13.03.P02", sketch=("set up vertical tangent", "solve")),
        ]
        questions = [make_question(year=2024.4, qno="7")]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=questions,
            kp_record=None,
            narrative=None,
        )
        # Three deterministic bullets: most-recent past-paper hit, dominant
        # sketch step 1, fresh sketch step 1.
        assert len(sheet.drill_set) == 3
        assert "2024 Jun" in sheet.drill_set[0]
        assert "Q7" in sheet.drill_set[0]
        assert "differentiate" in sheet.drill_set[1]
        assert "set up vertical tangent" in sheet.drill_set[2]


# ---------------------------------------------------------------------------
# Open caveats
# ---------------------------------------------------------------------------


class TestOpenCaveats:
    def test_caveats_merge_warnings_with_curriculum_only_reasons(self):
        posterior = make_posterior(
            tier="not_tested",
            n_papers=3,
            raw_hits=0,
            tier_reasons=(
                "no exam evidence; curriculum-only inference",
            ),
            warnings=("effective_N=1.20 < 2; prior dominates posterior",),
        )
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        joined = " | ".join(sheet.open_caveats)
        assert "curriculum-only" in joined
        assert "effective_N" in joined or "prior dominates" in joined

    def test_caveats_pick_up_single_paper_and_all_positive_warnings(self):
        posterior = make_posterior(
            n_papers=5,
            raw_hits=5,
            tier_reasons=("posterior_mean=0.95 >= 0.75", "ci_lower=0.50 >= 0.50"),
            warnings=(
                "all observations positive; CI narrowness reflects prior, not data",
            ),
        )
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        joined = " | ".join(sheet.open_caveats)
        assert "all observations positive" in joined


# ---------------------------------------------------------------------------
# Build all + variant rationale
# ---------------------------------------------------------------------------


class TestBuildAll:
    def test_one_entry_per_posterior_keyed_by_kp_id(self):
        posteriors = [
            make_posterior(kp_id="L13.03", tier="anchor"),
            make_posterior(kp_id="L14.01", tier="core"),
        ]
        sheets = build_all_cheatsheets(
            posteriors=posteriors,
            pattern_coverages=[],
            pattern_definitions=[],
            mapping_questions=[],
            kps=[
                {"kp_id": "L13.03", "label": "Tangent / Normal", "lecture_prefix": "Lecture 13"},
                {"kp_id": "L14.01", "label": "Implicit differentiation"},
            ],
            narratives={"L13.03": {"headline": "anchor narrative"}},
        )
        assert set(sheets.keys()) == {"L13.03", "L14.01"}
        assert sheets["L13.03"].kp_label == "Tangent / Normal"
        assert sheets["L13.03"].lecture_ref == "Lecture 13"
        assert sheets["L13.03"].headline == "anchor narrative"
        assert sheets["L14.01"].headline.startswith("Tier core")

    def test_variant_rationale_strings_reflect_pattern_tier(self):
        posterior = make_posterior()
        coverages = [
            make_coverage(
                pattern_id="L13.03.P01",
                tier="saturated",
                predicted_score=0.9,
                raw_hits=3,
                last_seen_year=2025.4,
            ),
            make_coverage(
                pattern_id="L13.03.P02",
                tier="hot",
                predicted_score=0.6,
                raw_hits=2,
                first_seen_year=2020.0,
                last_seen_year=2024.4,
            ),
            make_coverage(
                pattern_id="L13.03.P03",
                tier="fresh",
                predicted_score=0.3,
                freshness_flag=True,
            ),
            make_coverage(pattern_id="L13.03.P04", tier="dormant", predicted_score=0.05),
        ]
        patterns = [
            make_pattern("L13.03.P01"),
            make_pattern("L13.03.P02"),
            make_pattern("L13.03.P03", sources=("textbook §5.4 ex 14",)),
            make_pattern("L13.03.P04"),
        ]
        sheet = build_kp_cheatsheet(
            posterior=posterior,
            pattern_coverages=coverages,
            pattern_definitions=patterns,
            mapping_questions=[],
            kp_record=None,
            narrative=None,
        )
        assert "saturated" in sheet.saturated_patterns[0].rationale
        assert "2025 Jun" in sheet.saturated_patterns[0].rationale
        assert "hot" in sheet.hot_patterns[0].rationale
        assert "across" in sheet.hot_patterns[0].rationale
        assert "never tested" in sheet.fresh_patterns[0].rationale
        assert "textbook §5.4 ex 14" in sheet.fresh_patterns[0].rationale
        assert "dormant" in sheet.dormant_patterns[0].rationale
