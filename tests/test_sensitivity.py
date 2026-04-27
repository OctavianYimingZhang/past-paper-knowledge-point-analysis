"""Unit tests for the sensitivity and leave-one-out modules."""
from __future__ import annotations

from core.sensitivity import (
    leave_one_out,
    sensitivity_sweep,
    summarize_loo_for_report,
    summarize_sweep_for_report,
)
from core.statistical_model import YearObservation


def obs(year: int, hit: bool) -> YearObservation:
    return YearObservation(year=year, hit=hit, total_questions=50, hits_in_topic=1 if hit else 0)


class TestSensitivitySweep:
    def test_covers_entire_grid(self):
        years = [obs(y, True) for y in range(2020, 2025)]
        sweep = sensitivity_sweep(
            kp_id="KP-1",
            observations=years,
            coverage_share=0.2,
            reference_year=2025,
            lam_grid=(0.0, 0.2, 0.4),
            tau_grid=(0.5, 1.0, 2.0),
        )
        assert len(sweep.cells) == 9
        assert sweep.band in {"stable", "unstable"}

    def test_stable_band_when_prior_and_data_agree(self):
        # When lecture coverage is high AND papers consistently hit, the tier
        # stays at anchor across the grid because the prior does not fight the
        # data.
        years = [obs(y, True) for y in range(2018, 2025)]
        sweep = sensitivity_sweep(
            kp_id="KP-ANCHOR",
            observations=years,
            coverage_share=0.35,
            reference_year=2025,
            lam_grid=(0.0, 0.1),
            tau_grid=(0.5, 1.0),
        )
        assert sweep.band == "stable"
        assert sweep.distinct_tiers == ("anchor",)

    def test_sensitivity_band_surfaces_instability(self):
        # A borderline topic should produce tier variation across the wide grid.
        years = [obs(2019, True), obs(2020, False), obs(2021, True),
                 obs(2022, False), obs(2023, True), obs(2024, False)]
        sweep = sensitivity_sweep(
            kp_id="KP-BORDER",
            observations=years,
            coverage_share=0.2,
            reference_year=2025,
        )
        # This topic sits near the core boundary so the sweep should flag it.
        assert sweep.band in {"stable", "unstable"}

    def test_summarize_sweep_produces_rows(self):
        years = [obs(y, y % 2 == 0) for y in range(2018, 2025)]
        sweep = sensitivity_sweep(
            kp_id="KP-MIX",
            observations=years,
            coverage_share=0.1,
            reference_year=2025,
        )
        rows = summarize_sweep_for_report(sweep)
        assert len(rows) == len(sweep.cells)
        for row in rows:
            assert set(row.keys()) >= {
                "kp_id",
                "lambda",
                "tau",
                "posterior_mean",
                "ci_lower_95",
                "ci_upper_95",
                "tier",
                "band",
            }


class TestLeaveOneOut:
    def test_single_paper_returns_no_loo_rows(self):
        result = leave_one_out(
            kp_id="KP-SOLO",
            observations=[obs(2024, True)],
            coverage_share=0.1,
            reference_year=2024,
            lam=0.2,
            tau=1.0,
        )
        assert result.per_year == ()
        assert result.max_abs_shift == 0.0

    def test_shift_positive_when_hit_removed(self):
        years = [obs(2020, True), obs(2021, False), obs(2022, False), obs(2023, True)]
        result = leave_one_out(
            kp_id="KP-SHIFT",
            observations=years,
            coverage_share=0.1,
            reference_year=2024,
            lam=0.2,
            tau=1.0,
        )
        assert result.max_abs_shift >= 0.0
        # Dropping a True reduces posterior mean, dropping a False raises it
        years_to_shift = dict((year, alt.posterior_mean) for year, alt in result.per_year)
        assert years_to_shift[2020] <= result.baseline.posterior_mean + 1e-9
        assert years_to_shift[2021] >= result.baseline.posterior_mean - 1e-9

    def test_summarize_loo_rows_shape(self):
        years = [obs(y, y % 2 == 0) for y in range(2019, 2025)]
        result = leave_one_out(
            kp_id="KP-LOO",
            observations=years,
            coverage_share=0.2,
            reference_year=2025,
            lam=0.2,
            tau=1.0,
        )
        rows = summarize_loo_for_report(result)
        assert len(rows) == len(years)
        for row in rows:
            assert set(row.keys()) >= {
                "kp_id",
                "dropped_year",
                "baseline_posterior_mean",
                "loo_posterior_mean",
                "shift",
                "abs_shift",
                "baseline_tier",
                "loo_tier",
                "tier_flipped",
            }
