"""Unit tests for the pure statistical model."""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.statistical_model import (
    ALL_TIERS,
    YearObservation,
    analyze_kp,
    assign_tier,
    beta_credible_interval,
    build_curriculum_prior,
    compute_hotness,
    recency_weights,
    trend_split_half,
    weighted_beta_posterior,
)


def make_obs(year: int, hit: bool, total: int = 50, hits_in_topic: int | None = None) -> YearObservation:
    return YearObservation(
        year=year,
        hit=hit,
        total_questions=total,
        hits_in_topic=hits_in_topic if hits_in_topic is not None else (1 if hit else 0),
    )


class TestRecencyWeights:
    def test_lambda_zero_is_uniform(self):
        w = recency_weights(np.array([2020, 2021, 2022]), reference_year=2022, lam=0.0)
        assert np.allclose(w, [1.0, 1.0, 1.0])

    def test_lambda_positive_decays_older(self):
        w = recency_weights(np.array([2020, 2022]), reference_year=2022, lam=0.5)
        assert w[1] > w[0]
        assert math.isclose(w[0], math.exp(-0.5 * 2), rel_tol=1e-9)
        assert math.isclose(w[1], 1.0, rel_tol=1e-9)

    def test_negative_lambda_rejected(self):
        with pytest.raises(ValueError):
            recency_weights(np.array([2020]), reference_year=2020, lam=-0.1)

    def test_future_year_rejected(self):
        with pytest.raises(ValueError):
            recency_weights(np.array([2025]), reference_year=2020, lam=0.2)

    def test_empty_input_returns_empty(self):
        w = recency_weights(np.array([]), reference_year=2020, lam=0.2)
        assert w.size == 0


class TestBetaPosterior:
    def test_lambda_zero_matches_empirical_rate(self):
        obs = [make_obs(2020, True), make_obs(2021, False), make_obs(2022, True)]
        a, b, eh, en = weighted_beta_posterior(
            obs, reference_year=2022, lam=0.0, prior_alpha=0.0, prior_beta=0.0
        )
        assert math.isclose(eh, 2.0, rel_tol=1e-9)
        assert math.isclose(en, 3.0, rel_tol=1e-9)
        assert math.isclose(a, 2.0, rel_tol=1e-9)
        assert math.isclose(b, 1.0, rel_tol=1e-9)

    def test_empty_returns_prior(self):
        a, b, eh, en = weighted_beta_posterior(
            [], reference_year=2022, lam=0.2, prior_alpha=1.0, prior_beta=1.0
        )
        assert a == 1.0 and b == 1.0 and eh == 0.0 and en == 0.0

    def test_weight_override_applied(self):
        obs = [
            YearObservation(year=2020, hit=True, total_questions=50, hits_in_topic=1, weight_override=0.3),
            YearObservation(year=2021, hit=True, total_questions=50, hits_in_topic=1),
        ]
        _, _, eh, en = weighted_beta_posterior(
            obs, reference_year=2021, lam=0.0, prior_alpha=0.0, prior_beta=0.0
        )
        assert math.isclose(eh, 1.3, rel_tol=1e-9)
        assert math.isclose(en, 1.3, rel_tol=1e-9)


class TestCredibleInterval:
    def test_bounds_are_in_unit_interval(self):
        low, high = beta_credible_interval(3.0, 2.0)
        assert 0.0 <= low <= high <= 1.0

    def test_degenerate_returns_full_range(self):
        low, high = beta_credible_interval(0.0, 0.0)
        assert (low, high) == (0.0, 1.0)

    def test_symmetric_around_half_for_symmetric_beta(self):
        low, high = beta_credible_interval(5.0, 5.0, level=0.95)
        assert math.isclose(low + high, 1.0, abs_tol=1e-9)


class TestCurriculumPrior:
    def test_tau_zero_is_uniform(self):
        a, b = build_curriculum_prior(coverage_share=0.3, tau=0.0)
        assert (a, b) == (1.0, 1.0)

    def test_high_tau_rejected(self):
        with pytest.raises(ValueError):
            build_curriculum_prior(coverage_share=0.5, tau=2.5)

    def test_floor_keeps_prior_proper(self):
        a, b = build_curriculum_prior(coverage_share=0.0, tau=1.0)
        assert a > 0.0 and b > 0.0

    def test_prior_mean_tracks_coverage(self):
        a, b = build_curriculum_prior(coverage_share=0.7, tau=1.0)
        mean = a / (a + b)
        assert math.isclose(mean, 0.7, abs_tol=0.05)


class TestHotness:
    def test_empty(self):
        assert compute_hotness([]) == (0.0, 0.0)

    def test_normalizes_paper_length(self):
        obs = [make_obs(2020, True, total=50, hits_in_topic=5),
               make_obs(2021, True, total=25, hits_in_topic=5)]
        mean, std = compute_hotness(obs)
        # Paper 1: 0.1, Paper 2: 0.2 -> mean 0.15
        assert math.isclose(mean, 0.15, abs_tol=1e-9)
        assert std > 0.0


class TestTrend:
    def test_insufficient_for_small_n(self):
        obs = [make_obs(y, True) for y in [2020, 2021]]
        label, delta, ci = trend_split_half(obs, reference_year=2021)
        assert label == "insufficient"
        assert delta == 0.0

    def test_rising_detects_clear_increase(self):
        obs = [
            make_obs(2018, False), make_obs(2019, False),
            make_obs(2020, False), make_obs(2021, False),
            make_obs(2022, True), make_obs(2023, True),
            make_obs(2024, True), make_obs(2025, True),
        ]
        label, delta, _ = trend_split_half(obs, reference_year=2025)
        assert label == "rising"
        assert delta > 0.0

    def test_stable_when_mixed(self):
        obs = [
            make_obs(2020, True), make_obs(2021, False),
            make_obs(2022, True), make_obs(2023, False),
        ]
        label, _, _ = trend_split_half(obs, reference_year=2023)
        assert label == "stable"


class TestTierAssignment:
    def test_anchor(self):
        tier, reasons = assign_tier(
            post_mean=0.82, ci_low=0.55, ci_high=0.95, raw_hits=6,
            trend_label="stable", historical_mean=0.86, has_exam_evidence=True,
        )
        assert tier == "anchor"
        assert any("0.75" in r for r in reasons)

    def test_core(self):
        tier, _ = assign_tier(
            post_mean=0.60, ci_low=0.30, ci_high=0.80, raw_hits=3,
            trend_label="stable", historical_mean=0.60, has_exam_evidence=True,
        )
        assert tier == "core"

    def test_emerging(self):
        tier, _ = assign_tier(
            post_mean=0.35, ci_low=0.10, ci_high=0.60, raw_hits=2,
            trend_label="rising", historical_mean=0.25, has_exam_evidence=True,
        )
        assert tier == "emerging"

    def test_legacy(self):
        tier, _ = assign_tier(
            post_mean=0.30, ci_low=0.05, ci_high=0.55, raw_hits=3,
            trend_label="cooling", historical_mean=0.60, has_exam_evidence=True,
        )
        assert tier == "legacy"

    def test_oneoff(self):
        tier, _ = assign_tier(
            post_mean=0.20, ci_low=0.02, ci_high=0.50, raw_hits=1,
            trend_label="stable", historical_mean=0.20, has_exam_evidence=True,
        )
        assert tier == "oneoff"

    def test_not_tested_without_evidence(self):
        tier, _ = assign_tier(
            post_mean=0.5, ci_low=0.3, ci_high=0.7, raw_hits=0,
            trend_label="insufficient", historical_mean=0.0, has_exam_evidence=False,
        )
        assert tier == "not_tested"


class TestAnalyzeKP:
    def test_produces_all_expected_fields(self):
        obs = [make_obs(y, True) for y in range(2019, 2025)]
        res = analyze_kp(
            kp_id="KP-TEST",
            observations=obs,
            coverage_share=0.15,
            reference_year=2025,
            lam=0.2,
            tau=1.0,
        )
        assert res.kp_id == "KP-TEST"
        assert res.tier in ALL_TIERS
        assert 0.0 <= res.ci_lower_95 <= res.posterior_mean <= res.ci_upper_95 <= 1.0
        assert res.n_papers == 6
        assert res.raw_hits == 6
        assert res.sensitivity_band == "unknown"

    def test_empty_observations_are_not_tested(self):
        res = analyze_kp(
            kp_id="KP-EMPTY",
            observations=[],
            coverage_share=0.3,
            reference_year=2025,
        )
        assert res.tier == "not_tested"
        assert res.n_papers == 0
        assert "no papers supplied" in "".join(res.warnings)

    def test_single_paper_warns(self):
        obs = [make_obs(2024, True)]
        res = analyze_kp(
            kp_id="KP-SINGLE",
            observations=obs,
            coverage_share=0.05,
            reference_year=2024,
        )
        assert res.trend_label == "insufficient"
        assert any("single paper" in w for w in res.warnings)

    def test_lambda_zero_tau_zero_matches_empirical_mean(self):
        obs = [
            make_obs(2018, True), make_obs(2019, True),
            make_obs(2020, False), make_obs(2021, True),
            make_obs(2022, False),
        ]
        res = analyze_kp(
            kp_id="KP-MATCH",
            observations=obs,
            coverage_share=0.1,
            reference_year=2022,
            lam=0.0,
            tau=0.0,
        )
        # tau=0 -> uniform Beta(1,1). With 3 hits in 5 trials -> (1+3)/(1+1+5)=4/7
        expected = (1.0 + 3.0) / (1.0 + 1.0 + 5.0)
        assert math.isclose(res.posterior_mean, expected, rel_tol=1e-9)

    def test_degenerate_all_positive_triggers_warning(self):
        obs = [make_obs(y, True) for y in range(2020, 2024)]
        res = analyze_kp(
            kp_id="KP-ALLPOS",
            observations=obs,
            coverage_share=0.1,
            reference_year=2023,
        )
        assert any("all observations positive" in w for w in res.warnings)

    def test_duplicate_year_rejected(self):
        obs = [make_obs(2020, True), make_obs(2020, False)]
        with pytest.raises(ValueError):
            analyze_kp("KP-DUP", obs, coverage_share=0.1, reference_year=2020)

    def test_future_reference_year_rejected(self):
        obs = [make_obs(2025, True)]
        with pytest.raises(ValueError):
            analyze_kp("KP-FUTURE", obs, coverage_share=0.1, reference_year=2020)

    def test_ci_bounds_are_always_in_unit_interval(self):
        for hits in range(6):
            obs = [make_obs(2020 + i, i < hits) for i in range(5)]
            res = analyze_kp("KP-CI", obs, coverage_share=0.2, reference_year=2024)
            assert 0.0 <= res.ci_lower_95 <= res.posterior_mean <= res.ci_upper_95 <= 1.0
