"""Pure statistical model for past-paper knowledge-point prediction.

This module is intentionally I/O-free. Every function takes primitive inputs
(or frozen dataclasses) and returns frozen dataclasses. It is safe to unit
test in isolation, reproducible across runs, and free of any LLM calls.

The core model is a moment-matched Beta posterior over per-year
appearance indicators for each knowledge point (KP). The "moment-matched"
wording is deliberate: because recency weights are real-valued rather than
integer counts, the posterior is NOT a strict conjugate Beta. It is an
approximation chosen for tractability and interpretability. Every output
row records the hyperparameters used so results are auditable.

See references/methodology.md for the full justification.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Literal

import numpy as np
from scipy import stats

Tier = Literal[
    "anchor",
    "core",
    "emerging",
    "legacy",
    "oneoff",
    "not_tested",
]

TrendLabel = Literal["rising", "cooling", "stable", "insufficient"]

ALL_TIERS: tuple[Tier, ...] = (
    "anchor",
    "core",
    "emerging",
    "legacy",
    "oneoff",
    "not_tested",
)


@dataclass(frozen=True)
class YearObservation:
    """One paper-year worth of evidence for a single knowledge point."""

    year: int
    hit: bool
    total_questions: int
    hits_in_topic: int
    syllabus_version: str | None = None
    weight_override: float | None = None  # optional down-weight for syllabus changes


@dataclass(frozen=True)
class KPPosterior:
    """Fully audited posterior row for a single knowledge point."""

    kp_id: str
    n_papers: int
    raw_hits: int
    weighted_hits: float
    weighted_N: float
    lambda_used: float
    tau_used: float
    reference_year: int
    coverage_share: float
    prior_alpha: float
    prior_beta: float
    posterior_alpha: float
    posterior_beta: float
    posterior_mean: float
    ci_lower_95: float
    ci_upper_95: float
    hotness_mean_share: float
    hotness_std_share: float
    trend_label: TrendLabel
    trend_delta: float
    trend_ci_95: tuple[float, float]
    historical_mean: float
    tier: Tier
    tier_reasons: tuple[str, ...]
    sensitivity_band: Literal["stable", "unstable", "unknown"]
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def recency_weights(years: np.ndarray, reference_year: int, lam: float) -> np.ndarray:
    """Exponential-decay recency weights w_i = exp(-lambda * (ref - year_i)).

    Years are expected to be <= reference_year. A negative lag indicates a
    caller bug and raises ValueError.
    """
    if lam < 0.0 or lam > 2.0:
        raise ValueError(
            f"lambda must be in [0, 2]; got {lam}. Values outside this range "
            "are not statistically defensible for this pipeline."
        )
    years_arr = np.asarray(years, dtype=np.float64)
    if years_arr.size == 0:
        return np.zeros(0, dtype=np.float64)
    lags = float(reference_year) - years_arr
    if np.any(lags < 0):
        offenders = years_arr[lags < 0].tolist()
        raise ValueError(
            f"reference_year={reference_year} is earlier than years={offenders}. "
            "Set reference_year >= max(years)."
        )
    return np.exp(-lam * lags)


def _validate_observations(observations: Iterable[YearObservation]) -> list[YearObservation]:
    obs = list(observations)
    years = [o.year for o in obs]
    if len(set(years)) != len(years):
        duplicates = sorted({y for y in years if years.count(y) > 1})
        raise ValueError(f"Duplicate years in observations: {duplicates}")
    for o in obs:
        if o.total_questions < 0:
            raise ValueError(f"total_questions must be >=0; got {o.total_questions} for year {o.year}")
        if o.hits_in_topic < 0:
            raise ValueError(f"hits_in_topic must be >=0; got {o.hits_in_topic} for year {o.year}")
        if o.hits_in_topic > o.total_questions and o.total_questions > 0:
            raise ValueError(
                f"hits_in_topic ({o.hits_in_topic}) exceeds total_questions "
                f"({o.total_questions}) for year {o.year}"
            )
        if o.weight_override is not None and o.weight_override < 0:
            raise ValueError(f"weight_override must be >=0; got {o.weight_override} for year {o.year}")
    return sorted(obs, key=lambda o: o.year)


def weighted_beta_posterior(
    observations: list[YearObservation],
    reference_year: int,
    lam: float,
    prior_alpha: float,
    prior_beta: float,
) -> tuple[float, float, float, float]:
    """Moment-matched Beta posterior from recency-weighted observations.

    Returns (posterior_alpha, posterior_beta, effective_hits, effective_N).
    This is NOT strict conjugate updating because weights are real-valued.
    It is a moment-match: posterior mean equals (prior_alpha + effective_hits)
    / (prior_alpha + prior_beta + effective_N). Equivalent to pretending the
    weighted likelihood came from fractional pseudo-trials.
    """
    if not observations:
        return prior_alpha, prior_beta, 0.0, 0.0
    years = np.array([o.year for o in observations], dtype=np.float64)
    hits = np.array([1.0 if o.hit else 0.0 for o in observations], dtype=np.float64)
    base_weights = recency_weights(years, reference_year, lam)
    overrides = np.array(
        [1.0 if o.weight_override is None else float(o.weight_override) for o in observations],
        dtype=np.float64,
    )
    weights = base_weights * overrides
    effective_hits = float(np.sum(weights * hits))
    effective_N = float(np.sum(weights))
    post_alpha = prior_alpha + effective_hits
    post_beta = prior_beta + max(effective_N - effective_hits, 0.0)
    return post_alpha, post_beta, effective_hits, effective_N


def beta_credible_interval(alpha: float, beta: float, level: float = 0.95) -> tuple[float, float]:
    """Equal-tailed credible interval from a Beta(alpha, beta) distribution.

    Falls back to (0.0, 1.0) if parameters are degenerate (both <= 0).
    """
    if alpha <= 0 or beta <= 0:
        return 0.0, 1.0
    tail = (1.0 - level) / 2.0
    lower = float(stats.beta.ppf(tail, alpha, beta))
    upper = float(stats.beta.ppf(1.0 - tail, alpha, beta))
    # Numerical safety clamp to [0, 1].
    lower = max(0.0, min(1.0, lower))
    upper = max(0.0, min(1.0, upper))
    return lower, upper


def build_curriculum_prior(
    coverage_share: float,
    tau: float = 1.0,
    floor: float = 0.02,
) -> tuple[float, float]:
    """Translate lecture coverage share into a weak Beta prior.

    tau is capped at 2.0 to keep this honestly a "regularization prior" rather
    than an empirical one. tau=0 collapses to an improper no-op; callers should
    use Beta(1,1) in that case. The floor keeps coverage=0 from producing a
    degenerate all-beta prior.
    """
    if tau < 0.0 or tau > 2.0:
        raise ValueError(
            f"tau must be in [0, 2]; got {tau}. Higher values smuggle unjustified "
            "prior mass into the posterior."
        )
    if coverage_share < 0.0 or coverage_share > 1.0:
        raise ValueError(f"coverage_share must be in [0, 1]; got {coverage_share}")
    if tau == 0.0:
        return 1.0, 1.0  # Uniform prior
    share = max(floor, min(1.0 - floor, coverage_share))
    return tau * share, tau * (1.0 - share)


def compute_hotness(observations: list[YearObservation]) -> tuple[float, float]:
    """Mean and std of hits_in_topic / total_questions across papers.

    Returns (0.0, 0.0) when there is no exam data.
    """
    shares = []
    for o in observations:
        if o.total_questions <= 0:
            continue
        shares.append(o.hits_in_topic / o.total_questions)
    if not shares:
        return 0.0, 0.0
    arr = np.asarray(shares, dtype=np.float64)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    return mean, std


# ---------------------------------------------------------------------------
# Trend detection (split-halves with bootstrap CI, not Mann-Kendall)
# ---------------------------------------------------------------------------


def trend_split_half(
    observations: list[YearObservation],
    reference_year: int,
    n_bootstrap: int = 2000,
    rng: np.random.Generator | None = None,
) -> tuple[TrendLabel, float, tuple[float, float]]:
    """Split observations into older and newer halves; bootstrap the rate gap.

    Returns (label, delta, ci_95) where delta = rate_newer - rate_older.
    The label is "rising" only if the full 95% CI is > 0, "cooling" only if
    the full CI is < 0, "stable" otherwise. For n < 4 we return "insufficient"
    since the split cannot support either half with more than a single paper.
    """
    if len(observations) < 4:
        return "insufficient", 0.0, (0.0, 0.0)
    years = np.array([o.year for o in observations])
    hits = np.array([1.0 if o.hit else 0.0 for o in observations])
    order = np.argsort(years)
    years = years[order]
    hits = hits[order]
    mid = len(years) // 2
    old_hits, new_hits = hits[:mid], hits[mid:]
    delta = float(new_hits.mean() - old_hits.mean())

    rng = rng or np.random.default_rng(0xC0DEBA5E)
    boot_deltas = np.empty(n_bootstrap, dtype=np.float64)
    for i in range(n_bootstrap):
        old_sample = rng.choice(old_hits, size=old_hits.size, replace=True)
        new_sample = rng.choice(new_hits, size=new_hits.size, replace=True)
        boot_deltas[i] = new_sample.mean() - old_sample.mean()
    lower = float(np.quantile(boot_deltas, 0.025))
    upper = float(np.quantile(boot_deltas, 0.975))

    label: TrendLabel
    if lower > 0.0:
        label = "rising"
    elif upper < 0.0:
        label = "cooling"
    else:
        label = "stable"
    return label, delta, (lower, upper)


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------


def assign_tier(
    post_mean: float,
    ci_low: float,
    ci_high: float,
    raw_hits: int,
    trend_label: TrendLabel,
    historical_mean: float,
    has_exam_evidence: bool,
) -> tuple[Tier, tuple[str, ...]]:
    """Apply tier rules in priority order. Returns (tier, reasons)."""
    reasons: list[str] = []

    if not has_exam_evidence:
        reasons.append("no exam evidence; curriculum-only inference")
        return "not_tested", tuple(reasons)

    if post_mean >= 0.75 and ci_low >= 0.50:
        reasons.append(f"posterior_mean={post_mean:.2f} >= 0.75")
        reasons.append(f"ci_lower={ci_low:.2f} >= 0.50")
        return "anchor", tuple(reasons)

    if post_mean >= 0.50 and ci_low >= 0.25:
        reasons.append(f"posterior_mean={post_mean:.2f} >= 0.50")
        reasons.append(f"ci_lower={ci_low:.2f} >= 0.25")
        return "core", tuple(reasons)

    if trend_label == "rising" and post_mean >= 0.30:
        reasons.append("trend=rising")
        reasons.append(f"posterior_mean={post_mean:.2f} >= 0.30")
        return "emerging", tuple(reasons)

    if trend_label == "cooling" and historical_mean >= 0.50 and post_mean < 0.40:
        reasons.append("trend=cooling")
        reasons.append(f"historical_mean={historical_mean:.2f} >= 0.50")
        reasons.append(f"posterior_mean={post_mean:.2f} < 0.40")
        return "legacy", tuple(reasons)

    if raw_hits == 1:
        reasons.append("raw_hits=1 and no stronger signal")
        return "oneoff", tuple(reasons)

    if raw_hits == 0:
        reasons.append("raw_hits=0")
        return "not_tested", tuple(reasons)

    # raw_hits >= 2 but no higher tier matched: evidence too diffuse for core.
    reasons.append(
        f"multiple hits ({raw_hits}) but posterior_mean={post_mean:.2f} with "
        f"ci_lower={ci_low:.2f} fails core band"
    )
    return "oneoff", tuple(reasons)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def analyze_kp(
    kp_id: str,
    observations: Iterable[YearObservation],
    coverage_share: float,
    reference_year: int,
    lam: float = 0.2,
    tau: float = 1.0,
    bootstrap_rng: np.random.Generator | None = None,
) -> KPPosterior:
    """Compose the full KP analysis from raw observations.

    Always returns a KPPosterior with warnings populated for edge cases
    rather than raising, except for caller bugs (negative counts, duplicate
    years, reference year before last observation).
    """
    obs = _validate_observations(observations)
    n_papers = len(obs)
    raw_hits = sum(1 for o in obs if o.hit)

    warnings: list[str] = []

    prior_alpha, prior_beta = build_curriculum_prior(coverage_share, tau=tau)
    post_alpha, post_beta, eff_hits, eff_N = weighted_beta_posterior(
        obs,
        reference_year=reference_year,
        lam=lam,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
    )
    # Guard against degenerate posteriors from tau=0 and no data.
    if post_alpha + post_beta <= 0:
        warnings.append("degenerate posterior; falling back to uniform Beta(1,1)")
        post_alpha, post_beta = 1.0, 1.0

    post_mean = post_alpha / (post_alpha + post_beta)
    ci_low, ci_high = beta_credible_interval(post_alpha, post_beta, level=0.95)

    hotness_mean, hotness_std = compute_hotness(obs)

    if n_papers == 0:
        warnings.append("no papers supplied; output is prior-only")
        trend_label: TrendLabel = "insufficient"
        trend_delta = 0.0
        trend_ci: tuple[float, float] = (0.0, 0.0)
    elif n_papers == 1:
        warnings.append("single paper; trend and bootstrap disabled")
        trend_label = "insufficient"
        trend_delta = 0.0
        trend_ci = (0.0, 0.0)
    else:
        trend_label, trend_delta, trend_ci = trend_split_half(
            obs, reference_year, rng=bootstrap_rng
        )

    if n_papers > 0 and eff_N < 2.0:
        warnings.append(
            f"effective_N={eff_N:.2f} < 2; prior dominates posterior"
        )
    if coverage_share == 0.0 and raw_hits == 0:
        warnings.append("no coverage signal and no exam hits; result is not informative")
    if all(o.hit for o in obs) and n_papers >= 2:
        warnings.append("all observations positive; CI narrowness reflects prior, not data")
    if all(not o.hit for o in obs) and n_papers >= 2:
        warnings.append("all observations negative; CI narrowness reflects prior, not data")
    versions = {o.syllabus_version for o in obs if o.syllabus_version}
    if len(versions) > 1:
        warnings.append(
            f"mixed syllabus versions present: {sorted(versions)}; consider weight_override"
        )

    historical_hits_fraction = (raw_hits / n_papers) if n_papers > 0 else 0.0

    tier, reasons = assign_tier(
        post_mean=post_mean,
        ci_low=ci_low,
        ci_high=ci_high,
        raw_hits=raw_hits,
        trend_label=trend_label,
        historical_mean=historical_hits_fraction,
        has_exam_evidence=n_papers > 0,
    )

    return KPPosterior(
        kp_id=kp_id,
        n_papers=n_papers,
        raw_hits=raw_hits,
        weighted_hits=eff_hits,
        weighted_N=eff_N,
        lambda_used=lam,
        tau_used=tau,
        reference_year=reference_year,
        coverage_share=coverage_share,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        posterior_alpha=post_alpha,
        posterior_beta=post_beta,
        posterior_mean=post_mean,
        ci_lower_95=ci_low,
        ci_upper_95=ci_high,
        hotness_mean_share=hotness_mean,
        hotness_std_share=hotness_std,
        trend_label=trend_label,
        trend_delta=trend_delta,
        trend_ci_95=trend_ci,
        historical_mean=historical_hits_fraction,
        tier=tier,
        tier_reasons=reasons,
        sensitivity_band="unknown",  # set later by sensitivity sweep caller
        warnings=tuple(warnings),
    )


def with_sensitivity_band(posterior: KPPosterior, band: Literal["stable", "unstable"]) -> KPPosterior:
    """Return a copy of the posterior with an updated sensitivity_band."""
    return replace(posterior, sensitivity_band=band)
