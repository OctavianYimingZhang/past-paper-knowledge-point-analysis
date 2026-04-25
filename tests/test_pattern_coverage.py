"""Unit tests for the pattern-coverage layer.

The pattern layer is honest frequency + recency + freshness. There is no
posterior to test, so these tests exercise:

* Recency weighting under the same lambda as the KP layer.
* Saturation index growing with recent and adjacent hits.
* Freshness flag firing only when the pattern is seeded by material AND
  unseen / stale.
* Predicted score behaviour under varying alpha (novelty bias).
* The pattern-tier rules (`saturated / hot / fresh / dormant`).
* End-to-end `compute_kp_pattern_coverage` over multiple patterns.
"""
from __future__ import annotations

import math

import pytest

from scripts.pattern_coverage import (
    HOT_PREDICTED_MULTIPLIER,
    PATTERN_TIERS,
    PatternOccurrence,
    SATURATION_TIER_THRESHOLD,
    assign_pattern_tier,
    compute_kp_pattern_coverage,
    compute_pattern_coverage,
    coverage_to_jsonable,
)


REF_YEAR = 2026.0
LAM = 0.2


def make_occ(
    year: float,
    *,
    qno: str = "1",
    confidence: float = 1.0,
    is_primary: bool = True,
    complications: tuple[str, ...] = (),
) -> PatternOccurrence:
    return PatternOccurrence(
        year=year,
        question_number=qno,
        confidence=confidence,
        is_primary=is_primary,
        complications=complications,
    )


class TestEmpty:
    def test_zero_hits_seeded_returns_fresh(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P02",
            occurrences=(),
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        assert cov.raw_hits == 0
        assert cov.weighted_hits == 0.0
        assert cov.last_seen_year is None
        assert cov.first_seen_year is None
        assert cov.inter_arrival_years_mean is None
        assert cov.saturation_index == 0.0
        assert cov.freshness_flag is True
        assert cov.warnings == ()

    def test_zero_hits_unseeded_emits_warning(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P99",
            occurrences=(),
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=False,
        )
        assert cov.freshness_flag is False
        assert any("not seeded" in w for w in cov.warnings)


class TestSingleHit:
    def test_recent_hit_no_saturation(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P02",
            occurrences=[make_occ(2024.4)],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        assert cov.raw_hits == 1
        assert math.isclose(
            cov.weighted_hits, math.exp(-LAM * 1.6), rel_tol=1e-3
        )
        assert cov.last_seen_year == 2024.4
        assert cov.first_seen_year == 2024.4
        assert cov.inter_arrival_years_mean is None  # need 2+ hits
        assert cov.saturation_index < 0.5  # single recent hit only
        assert cov.freshness_flag is False  # within fresh_gap_years window

    def test_old_hit_seeded_is_fresh(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P02",
            occurrences=[make_occ(2014.0)],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            fresh_gap_years=4.0,
        )
        assert cov.raw_hits == 1
        assert cov.freshness_flag is True


class TestContiguousHits:
    def test_three_consecutive_recent_hits_saturate(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P02",
            occurrences=[
                make_occ(2023.4),
                make_occ(2024.4),
                make_occ(2025.4),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        assert cov.raw_hits == 3
        assert cov.saturation_index >= 0.6
        assert cov.freshness_flag is False
        assert cov.inter_arrival_years_max == pytest.approx(1.0)

    def test_alternates_count_at_half_weight(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P02",
            occurrences=[
                make_occ(2024.4, is_primary=True, confidence=1.0),
                make_occ(2025.4, is_primary=False, confidence=0.6),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        assert cov.raw_hits == 2
        # primary contributes exp(-0.2*1.6); alternate contributes
        # 0.5 * 0.6 * exp(-0.2*0.6).
        primary = math.exp(-LAM * 1.6)
        alt = 0.5 * 0.6 * math.exp(-LAM * 0.6)
        assert math.isclose(cov.weighted_hits, primary + alt, rel_tol=1e-3)


class TestGapThenRecur:
    def test_old_then_recent_keeps_freshness_off(self):
        cov = compute_pattern_coverage(
            kp_id="L13.03",
            pattern_id="L13.03.P02",
            occurrences=[
                make_occ(2014.0),
                make_occ(2024.4),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            fresh_gap_years=4.0,
        )
        # last_seen recent → not fresh.
        assert cov.freshness_flag is False
        assert cov.inter_arrival_years_max == pytest.approx(10.4)
        assert cov.inter_arrival_years_mean == pytest.approx(10.4)


class TestFreshnessFlag:
    @pytest.mark.parametrize(
        "fresh_gap_years,expected",
        [
            (4.0, False),  # last hit 2024.4 is within 4 years of 2026
            (1.0, True),  # last hit 2024.4 is more than 1 year stale
        ],
    )
    def test_fresh_gap_years_threshold(self, fresh_gap_years, expected):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[make_occ(2024.4)],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            fresh_gap_years=fresh_gap_years,
        )
        assert cov.freshness_flag is expected

    def test_unseeded_pattern_never_fresh(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=(),
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=False,
        )
        assert cov.freshness_flag is False


class TestPredictedScore:
    def test_alpha_zero_equals_weighted_hits(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[make_occ(2024.4)],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            alpha=0.0,
        )
        assert math.isclose(cov.predicted_score, cov.weighted_hits, rel_tol=1e-3)

    def test_alpha_downweights_saturated(self):
        sat = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[
                make_occ(2023.4),
                make_occ(2024.4),
                make_occ(2025.4),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            alpha=0.5,
        )
        no_alpha = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[
                make_occ(2023.4),
                make_occ(2024.4),
                make_occ(2025.4),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            alpha=0.0,
        )
        assert sat.predicted_score < no_alpha.predicted_score

    def test_alpha_uplifts_fresh(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=(),
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            alpha=0.4,
        )
        # weighted_hits = 0; freshness uplift = 0.4 * 0.5 = 0.2
        assert cov.predicted_score == pytest.approx(0.2, abs=1e-6)

    def test_alpha_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            compute_pattern_coverage(
                kp_id="K",
                pattern_id="K.P01",
                occurrences=(),
                reference_year=REF_YEAR,
                lam=LAM,
                seeded_in_material=True,
                alpha=1.5,
            )

    def test_lambda_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            compute_pattern_coverage(
                kp_id="K",
                pattern_id="K.P01",
                occurrences=(),
                reference_year=REF_YEAR,
                lam=2.5,
                seeded_in_material=True,
            )


class TestComplications:
    def test_seen_and_unseen_partition(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[
                make_occ(2024.4, complications=("perpendicular-line follow-up",)),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
            pattern_complications=(
                "perpendicular-line follow-up",
                "vertical-tangent edge case",
            ),
        )
        assert "perpendicular-line follow-up" in cov.complications_seen
        assert "vertical-tangent edge case" in cov.complications_unseen


class TestPatternTier:
    def test_saturated_tier_fires_on_high_index(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[
                make_occ(2023.4),
                make_occ(2024.4),
                make_occ(2025.4),
            ],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        tier, reasons = assign_pattern_tier(cov, kp_predicted_median=0.5)
        assert tier == "saturated"
        assert any("saturation_index" in r for r in reasons)

    def test_hot_tier_requires_predicted_score_above_median(self):
        # Two well-spaced recent hits, not adjacent: avoids the saturated rule.
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[make_occ(2020.0), make_occ(2024.4)],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        # Median below the predicted score → hot.
        tier, _ = assign_pattern_tier(cov, kp_predicted_median=0.1)
        assert tier == "hot"

    def test_fresh_tier_when_seeded_and_unseen(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=(),
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        tier, _ = assign_pattern_tier(cov, kp_predicted_median=0.5)
        assert tier == "fresh"

    def test_dormant_tier_when_unseen_and_unseeded(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=(),
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=False,
        )
        tier, _ = assign_pattern_tier(cov, kp_predicted_median=0.5)
        assert tier == "dormant"

    def test_pattern_tiers_constant_complete(self):
        assert set(PATTERN_TIERS) == {"saturated", "hot", "fresh", "dormant"}

    def test_thresholds_constants(self):
        assert 0.0 < SATURATION_TIER_THRESHOLD < 1.0
        assert HOT_PREDICTED_MULTIPLIER > 1.0


class TestEndToEnd:
    def test_compute_kp_pattern_coverage_assigns_tiers(self):
        patterns = [
            {
                "pattern_id": "K.P01",
                "common_complications": ["complication-a"],
                "source": ["textbook §1.1"],
            },
            {
                "pattern_id": "K.P02",
                "common_complications": [],
                "source": ["textbook §1.2"],
            },
            {
                "pattern_id": "K.P03",
                "common_complications": [],
                "source": [],
            },
        ]
        questions = [
            {
                "year": 2023.4,
                "question_number": "5",
                "primary_kp": "K",
                "pattern_id": "K.P01",
                "alt_pattern_ids": [],
                "confidence": 0.9,
                "complications": ["complication-a"],
            },
            {
                "year": 2024.4,
                "question_number": "5",
                "primary_kp": "K",
                "pattern_id": "K.P01",
                "alt_pattern_ids": [],
                "confidence": 0.9,
                "complications": [],
            },
            {
                "year": 2025.4,
                "question_number": "5",
                "primary_kp": "K",
                "pattern_id": "K.P01",
                "alt_pattern_ids": [],
                "confidence": 0.9,
                "complications": [],
            },
        ]
        rows = compute_kp_pattern_coverage(
            kp_id="K",
            patterns=patterns,
            mapping_questions=questions,
            reference_year=REF_YEAR,
            lam=LAM,
            alpha=0.3,
        )
        assert len(rows) == 3
        by_id = {r.pattern_id: r for r in rows}
        assert by_id["K.P01"].tier == "saturated"
        assert by_id["K.P02"].tier == "fresh"  # seeded, unseen
        # P03 not seeded and not seen -> dormant; carries warning.
        assert by_id["K.P03"].tier == "dormant"
        assert all(r.tier_reasons for r in rows)

    def test_alt_pattern_in_secondary_position_counted_at_half_weight(self):
        patterns = [
            {"pattern_id": "K.P01", "source": ["lecture L1"]},
            {"pattern_id": "K.P02", "source": ["lecture L2"]},
        ]
        questions = [
            {
                "year": 2024.4,
                "question_number": "5",
                "primary_kp": "K",
                "pattern_id": "K.P01",
                "alt_pattern_ids": [{"pattern_id": "K.P02", "confidence": 0.6}],
                "confidence": 0.9,
            }
        ]
        rows = compute_kp_pattern_coverage(
            kp_id="K",
            patterns=patterns,
            mapping_questions=questions,
            reference_year=REF_YEAR,
            lam=LAM,
            alpha=0.3,
        )
        by_id = {r.pattern_id: r for r in rows}
        # Alt confidence 0.6 → weight 0.5 * 0.6 = 0.3 of the primary's weight.
        primary = by_id["K.P01"].weighted_hits
        alt = by_id["K.P02"].weighted_hits
        assert alt == pytest.approx(0.3 * primary, rel=1e-2)


class TestJsonable:
    def test_jsonable_roundtrip_keys(self):
        cov = compute_pattern_coverage(
            kp_id="K",
            pattern_id="K.P01",
            occurrences=[make_occ(2024.4)],
            reference_year=REF_YEAR,
            lam=LAM,
            seeded_in_material=True,
        )
        # Manually assign a tier so the jsonable output reflects schema 2.
        from dataclasses import replace

        cov = replace(cov, tier="hot", tier_reasons=("predicted >= median",))
        payload = coverage_to_jsonable(cov)
        for required in (
            "kp_id",
            "pattern_id",
            "raw_hits",
            "weighted_hits",
            "last_seen_year",
            "first_seen_year",
            "inter_arrival_years_mean",
            "inter_arrival_years_max",
            "saturation_index",
            "freshness_flag",
            "predicted_score",
            "complications_seen",
            "complications_unseen",
            "occurrences",
            "warnings",
            "tier",
            "tier_reasons",
        ):
            assert required in payload, f"missing key: {required}"
        assert payload["tier"] == "hot"
