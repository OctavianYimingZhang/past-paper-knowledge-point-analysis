"""Sensitivity and stability analyses over the Beta-posterior model.

Every public function is pure: given observations and hyperparameters, it
returns dataclasses that can be rendered directly into report sheets.

Three analyses are exposed:

1. lambda/tau sweep: re-run analyze_kp across a grid of (lambda, tau) to
   see how the tier decision moves.
2. leave-one-out stability: drop one paper-year at a time and record how
   the posterior mean shifts.
3. sensitivity_band assignment: summarize the sweep into a stable vs
   unstable flag based on how many distinct tiers appear.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np

from .statistical_model import (
    ALL_TIERS,
    KPPosterior,
    Tier,
    YearObservation,
    analyze_kp,
    with_sensitivity_band,
)


DEFAULT_LAMBDA_GRID: tuple[float, ...] = (0.0, 0.2, 0.4)
DEFAULT_TAU_GRID: tuple[float, ...] = (0.5, 1.0, 2.0)


@dataclass(frozen=True)
class SensitivityCell:
    lam: float
    tau: float
    posterior_mean: float
    ci_lower_95: float
    ci_upper_95: float
    tier: Tier
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SensitivitySweep:
    kp_id: str
    cells: tuple[SensitivityCell, ...]
    distinct_tiers: tuple[Tier, ...]
    band: Literal["stable", "unstable"]

    @property
    def tier_counts(self) -> dict[Tier, int]:
        counts: dict[Tier, int] = {t: 0 for t in ALL_TIERS}
        for cell in self.cells:
            counts[cell.tier] += 1
        return counts


@dataclass(frozen=True)
class LeaveOneOutResult:
    kp_id: str
    baseline: KPPosterior
    per_year: tuple[tuple[int, KPPosterior], ...]
    max_abs_shift: float  # |posterior_mean - baseline_mean| worst case
    tier_flips: tuple[int, ...]  # years whose removal flips the tier


def sensitivity_sweep(
    kp_id: str,
    observations: list[YearObservation],
    coverage_share: float,
    reference_year: int,
    lam_grid: Iterable[float] = DEFAULT_LAMBDA_GRID,
    tau_grid: Iterable[float] = DEFAULT_TAU_GRID,
) -> SensitivitySweep:
    """Re-run analyze_kp on a (lambda, tau) grid and summarize stability."""
    cells: list[SensitivityCell] = []
    tiers_seen: set[Tier] = set()
    for lam in lam_grid:
        for tau in tau_grid:
            result = analyze_kp(
                kp_id=kp_id,
                observations=observations,
                coverage_share=coverage_share,
                reference_year=reference_year,
                lam=lam,
                tau=tau,
            )
            cells.append(
                SensitivityCell(
                    lam=lam,
                    tau=tau,
                    posterior_mean=result.posterior_mean,
                    ci_lower_95=result.ci_lower_95,
                    ci_upper_95=result.ci_upper_95,
                    tier=result.tier,
                    warnings=result.warnings,
                )
            )
            tiers_seen.add(result.tier)
    distinct = tuple(t for t in ALL_TIERS if t in tiers_seen)
    band: Literal["stable", "unstable"] = "stable" if len(distinct) <= 1 else "unstable"
    return SensitivitySweep(
        kp_id=kp_id,
        cells=tuple(cells),
        distinct_tiers=distinct,
        band=band,
    )


def leave_one_out(
    kp_id: str,
    observations: list[YearObservation],
    coverage_share: float,
    reference_year: int,
    lam: float,
    tau: float,
) -> LeaveOneOutResult:
    """Drop one observation at a time and re-run analyze_kp.

    Returns baseline posterior plus per-year re-analyses and a summary of
    how sensitive the result is to a single paper. Returns an empty
    per-year tuple when fewer than two observations exist.
    """
    baseline = analyze_kp(
        kp_id=kp_id,
        observations=observations,
        coverage_share=coverage_share,
        reference_year=reference_year,
        lam=lam,
        tau=tau,
    )
    if len(observations) < 2:
        return LeaveOneOutResult(
            kp_id=kp_id,
            baseline=baseline,
            per_year=(),
            max_abs_shift=0.0,
            tier_flips=(),
        )

    per_year: list[tuple[int, KPPosterior]] = []
    tier_flips: list[int] = []
    max_shift = 0.0
    for idx in range(len(observations)):
        held_out = observations[idx]
        remaining = observations[:idx] + observations[idx + 1 :]
        alt = analyze_kp(
            kp_id=kp_id,
            observations=remaining,
            coverage_share=coverage_share,
            reference_year=reference_year,
            lam=lam,
            tau=tau,
        )
        per_year.append((held_out.year, alt))
        shift = abs(alt.posterior_mean - baseline.posterior_mean)
        max_shift = max(max_shift, shift)
        if alt.tier != baseline.tier:
            tier_flips.append(held_out.year)

    return LeaveOneOutResult(
        kp_id=kp_id,
        baseline=baseline,
        per_year=tuple(per_year),
        max_abs_shift=max_shift,
        tier_flips=tuple(tier_flips),
    )


def apply_sensitivity_band(
    posterior: KPPosterior,
    sweep: SensitivitySweep,
) -> KPPosterior:
    """Attach the sweep's band to the primary posterior record."""
    if posterior.kp_id != sweep.kp_id:
        raise ValueError(
            f"sweep kp_id {sweep.kp_id} does not match posterior {posterior.kp_id}"
        )
    return with_sensitivity_band(posterior, sweep.band)


def summarize_sweep_for_report(sweep: SensitivitySweep) -> list[dict[str, object]]:
    """Flatten a sweep into per-cell dicts ready for Excel/JSON rendering."""
    rows: list[dict[str, object]] = []
    for cell in sweep.cells:
        rows.append(
            {
                "kp_id": sweep.kp_id,
                "lambda": cell.lam,
                "tau": cell.tau,
                "posterior_mean": round(cell.posterior_mean, 4),
                "ci_lower_95": round(cell.ci_lower_95, 4),
                "ci_upper_95": round(cell.ci_upper_95, 4),
                "tier": cell.tier,
                "warnings": "; ".join(cell.warnings),
                "band": sweep.band,
            }
        )
    return rows


def summarize_loo_for_report(result: LeaveOneOutResult) -> list[dict[str, object]]:
    """Flatten a leave-one-out result into per-year dicts for Excel/JSON."""
    rows: list[dict[str, object]] = []
    base = result.baseline
    for year, alt in result.per_year:
        rows.append(
            {
                "kp_id": result.kp_id,
                "dropped_year": year,
                "baseline_posterior_mean": round(base.posterior_mean, 4),
                "loo_posterior_mean": round(alt.posterior_mean, 4),
                "shift": round(alt.posterior_mean - base.posterior_mean, 4),
                "abs_shift": round(abs(alt.posterior_mean - base.posterior_mean), 4),
                "baseline_tier": base.tier,
                "loo_tier": alt.tier,
                "tier_flipped": alt.tier != base.tier,
            }
        )
    return rows


def mean_of_posteriors(posteriors: list[KPPosterior]) -> float:
    """Helper: compute mean of posterior_mean values across KPs (sanity checks)."""
    if not posteriors:
        return 0.0
    return float(np.mean([p.posterior_mean for p in posteriors]))
