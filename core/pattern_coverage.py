"""Pattern-level coverage and saturation statistics.

The KP-frequency layer (`statistical_model.py`) answers the question
"will this knowledge point appear next sitting?". This module answers the
sharper question "if it appears, *how* will it be tested?" by aggregating
the question-to-pattern mapping produced by the `pattern-classifier` Sonnet
subagent.

Per-pattern data is sparse: with 11-28 mapped years and 3-6 patterns per KP,
each cell typically carries 0-5 hits. A Beta posterior at this granularity
would be uselessly wide, so this module deliberately avoids credible
intervals and instead emits transparent statistics:

* weighted hit count under the same recency decay used by the KP layer
* last-seen and first-seen years
* inter-arrival statistics (mean and longest gap between hits)
* a saturation index combining recent density and reuse-cluster detection
* a freshness flag for textbook/lecture-seeded patterns the examiner has
  not used recently
* lists of complications already seen vs unseen

A novelty bias `alpha in [0, 1]` (default 0.3) softly downweights saturated
patterns and upweights fresh patterns when computing a `predicted_score`.
With `alpha = 0` the score reduces to weighted frequency — fully neutral.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np

PATTERN_TIERS: tuple[str, ...] = ("saturated", "hot", "fresh", "dormant")
SATURATION_TIER_THRESHOLD: float = 0.6
HOT_PREDICTED_MULTIPLIER: float = 1.25


@dataclass(frozen=True)
class PatternOccurrence:
    """A single past-paper appearance of a (KP, pattern) cell."""

    year: float
    question_number: str
    confidence: float
    is_primary: bool = True
    complications: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternCoverage:
    """Coverage statistics for a single (kp_id, pattern_id) cell."""

    kp_id: str
    pattern_id: str
    raw_hits: int
    weighted_hits: float
    last_seen_year: float | None
    first_seen_year: float | None
    inter_arrival_years_mean: float | None
    inter_arrival_years_max: float | None
    saturation_index: float
    freshness_flag: bool
    predicted_score: float
    complications_seen: tuple[str, ...]
    complications_unseen: tuple[str, ...]
    occurrences: tuple[PatternOccurrence, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    tier: str = ""
    tier_reasons: tuple[str, ...] = field(default_factory=tuple)


def _recency_weight(year: float, reference_year: float, lam: float) -> float:
    return float(np.exp(-lam * max(reference_year - year, 0.0)))


def _saturation_index(
    occurrences: list[PatternOccurrence],
    reference_year: float,
    lam: float,
) -> float:
    """Saturation = how 'used up' the pattern is.

    The score is bounded in [0, 1]. It rises with:
      * weighted hit count in the last 3 years (recent density)
      * presence of two or more hits within any 2-year window (reuse cluster)
    and falls with:
      * variation diversity (handled by the caller via the predicted score)

    Implementation detail: we combine a recent-density term and a cluster
    indicator term, then squash with `1 - exp(-x)` so the index is naturally
    in [0, 1].
    """
    if not occurrences:
        return 0.0
    years = sorted(o.year for o in occurrences)
    recent_density = sum(
        _recency_weight(y, reference_year, lam)
        for y in years
        if (reference_year - y) <= 3.0
    )
    cluster_term = 0.0
    for i in range(1, len(years)):
        gap = years[i] - years[i - 1]
        if gap <= 2.0:
            cluster_term += 1.0 - 0.5 * gap  # gap=0 -> 1.0, gap=2 -> 0.0
    raw = 0.6 * recent_density + 0.4 * cluster_term
    return float(1.0 - np.exp(-raw))


def _interarrivals(years: list[float]) -> tuple[float | None, float | None]:
    if len(years) < 2:
        return None, None
    sorted_years = sorted(years)
    gaps = [sorted_years[i] - sorted_years[i - 1] for i in range(1, len(sorted_years))]
    return float(np.mean(gaps)), float(max(gaps))


def compute_pattern_coverage(
    kp_id: str,
    pattern_id: str,
    occurrences: Iterable[PatternOccurrence],
    reference_year: float,
    lam: float,
    seeded_in_material: bool,
    pattern_complications: Iterable[str] = (),
    alpha: float = 0.3,
    fresh_gap_years: float = 4.0,
) -> PatternCoverage:
    """Compute the coverage row for one (kp_id, pattern_id) cell.

    Parameters
    ----------
    kp_id, pattern_id
        Cell identifiers.
    occurrences
        All past-paper appearances of this pattern (primary or alternate).
        Alternate alignments contribute at half-weight via `is_primary`.
    reference_year
        Float year used by the KP layer (Jan = .0, Jun = .4, Oct = .8).
    lam
        Recency decay rate, same as the KP layer.
    seeded_in_material
        True if the pattern is documented by textbook or lecture material.
        Required for the freshness flag — patterns invented out of thin air
        cannot be marked fresh.
    pattern_complications
        Canonical complications listed in the pattern definition.
    alpha
        Novelty-bias weight in [0, 1]. Default 0.3 (mild novelty preference).
    fresh_gap_years
        A pattern is fresh if it has zero hits OR was last seen more than
        `fresh_gap_years` ago.
    """
    if alpha < 0.0 or alpha > 1.0:
        raise ValueError(f"alpha must be in [0, 1]; got {alpha}")
    if lam < 0.0 or lam > 2.0:
        raise ValueError(f"lambda must be in [0, 2]; got {lam}")

    occ_list = sorted(occurrences, key=lambda o: o.year)
    raw_hits = len(occ_list)
    weighted_hits = 0.0
    for occ in occ_list:
        w = _recency_weight(occ.year, reference_year, lam)
        if not occ.is_primary:
            w *= 0.5 * max(0.0, min(1.0, occ.confidence))
        weighted_hits += w

    last_seen = occ_list[-1].year if occ_list else None
    first_seen = occ_list[0].year if occ_list else None
    mean_gap, max_gap = _interarrivals([o.year for o in occ_list])

    saturation = _saturation_index(occ_list, reference_year, lam)

    is_unseen = raw_hits == 0
    is_dormant = (
        last_seen is not None and (reference_year - last_seen) > fresh_gap_years
    )
    freshness = bool(seeded_in_material and (is_unseen or is_dormant))

    canonical = tuple(sorted({c for c in pattern_complications if c}))
    complications_seen = tuple(
        sorted({c for o in occ_list for c in o.complications if c})
    )
    complications_unseen = tuple(c for c in canonical if c not in complications_seen)

    # Predicted score = base recency-weighted frequency, modulated by novelty.
    predicted = weighted_hits
    if alpha > 0.0:
        predicted = predicted * (1.0 - alpha * saturation)
        if freshness:
            predicted += alpha * 0.5  # bounded fresh-pattern uplift

    warnings: list[str] = []
    if not seeded_in_material and raw_hits > 0:
        warnings.append(
            "pattern observed in papers but not seeded by material; "
            "consider adding to the textbook/lecture taxonomy"
        )
    if raw_hits == 0 and not seeded_in_material:
        warnings.append("pattern not observed and not seeded; degenerate row")

    return PatternCoverage(
        kp_id=kp_id,
        pattern_id=pattern_id,
        raw_hits=raw_hits,
        weighted_hits=round(weighted_hits, 4),
        last_seen_year=last_seen,
        first_seen_year=first_seen,
        inter_arrival_years_mean=(round(mean_gap, 3) if mean_gap is not None else None),
        inter_arrival_years_max=(round(max_gap, 3) if max_gap is not None else None),
        saturation_index=round(saturation, 4),
        freshness_flag=freshness,
        predicted_score=round(predicted, 4),
        complications_seen=complications_seen,
        complications_unseen=complications_unseen,
        occurrences=tuple(occ_list),
        warnings=tuple(warnings),
    )


def assign_pattern_tier(
    coverage: PatternCoverage,
    kp_predicted_median: float,
) -> tuple[str, tuple[str, ...]]:
    """Assign one of `saturated / hot / fresh / dormant` to a pattern row.

    The rules fire in priority order. The first matching rule wins.

    Pattern tiers are orthogonal to KP tiers — they describe *how* a topic
    is being tested, not *whether* it appears. See
    `references/tier-definitions.md` for the canonical rule table.
    """
    if (
        coverage.saturation_index >= SATURATION_TIER_THRESHOLD
        and coverage.raw_hits >= 2
    ):
        return "saturated", (
            f"saturation_index={coverage.saturation_index:.2f} "
            f">= {SATURATION_TIER_THRESHOLD:.2f}",
            f"raw_hits={coverage.raw_hits} >= 2",
        )

    hot_threshold = HOT_PREDICTED_MULTIPLIER * max(0.0, kp_predicted_median)
    if (
        coverage.raw_hits >= 2
        and coverage.predicted_score >= hot_threshold
        and hot_threshold > 0.0
    ):
        return "hot", (
            f"predicted_score={coverage.predicted_score:.2f} "
            f">= {hot_threshold:.2f} (kp_median*{HOT_PREDICTED_MULTIPLIER:.2f})",
            f"raw_hits={coverage.raw_hits} >= 2",
            f"saturation_index={coverage.saturation_index:.2f} "
            f"< {SATURATION_TIER_THRESHOLD:.2f}",
        )

    if coverage.freshness_flag:
        return "fresh", (
            "freshness_flag=True",
            "seeded by textbook or lecture; not seen within fresh_gap_years",
        )

    return "dormant", (
        f"raw_hits={coverage.raw_hits}",
        f"freshness_flag={coverage.freshness_flag}",
    )


def compute_kp_pattern_coverage(
    kp_id: str,
    patterns: list[dict],
    mapping_questions: list[dict],
    reference_year: float,
    lam: float,
    alpha: float = 0.3,
) -> list[PatternCoverage]:
    """Compute coverage rows for every pattern of a single KP.

    Parameters
    ----------
    patterns
        List of pattern definitions (dicts) for this KP. Each must include
        `pattern_id` and may include `common_complications` and `source`.
    mapping_questions
        Subset of `mapping.json` questions whose `primary_kp` is this KP.
        Each question dict may include `pattern_id`, `alt_pattern_ids`, and
        `complications` lists.
    """
    coverages: list[PatternCoverage] = []
    for pattern in patterns:
        pattern_id = pattern["pattern_id"]
        seeded = bool(pattern.get("source"))
        canonical_complications = pattern.get("common_complications", []) or []

        occurrences: list[PatternOccurrence] = []
        for question in mapping_questions:
            year = float(question.get("year", 0))
            qno = str(question.get("question_number", "?"))
            conf = float(question.get("confidence", 1.0))
            complications = tuple(question.get("complications") or ())

            primary_pid = question.get("pattern_id")
            if primary_pid == pattern_id:
                occurrences.append(
                    PatternOccurrence(
                        year=year,
                        question_number=qno,
                        confidence=conf,
                        is_primary=True,
                        complications=complications,
                    )
                )
                continue

            for alt in question.get("alt_pattern_ids") or []:
                alt_pid = alt.get("pattern_id") if isinstance(alt, dict) else alt
                if alt_pid != pattern_id:
                    continue
                alt_conf = (
                    float(alt.get("confidence", conf)) if isinstance(alt, dict) else conf
                )
                occurrences.append(
                    PatternOccurrence(
                        year=year,
                        question_number=qno,
                        confidence=alt_conf,
                        is_primary=False,
                        complications=complications,
                    )
                )

        coverages.append(
            compute_pattern_coverage(
                kp_id=kp_id,
                pattern_id=pattern_id,
                occurrences=occurrences,
                reference_year=reference_year,
                lam=lam,
                seeded_in_material=seeded,
                pattern_complications=canonical_complications,
                alpha=alpha,
            )
        )

    scores = [c.predicted_score for c in coverages]
    median_score = float(statistics.median(scores)) if scores else 0.0
    coverages = [
        replace(
            cov,
            tier=(t := assign_pattern_tier(cov, median_score))[0],
            tier_reasons=t[1],
        )
        for cov in coverages
    ]
    return coverages


def coverage_to_jsonable(coverage: PatternCoverage) -> dict:
    """Render a PatternCoverage as a JSON-serializable dict."""
    return {
        "kp_id": coverage.kp_id,
        "pattern_id": coverage.pattern_id,
        "raw_hits": coverage.raw_hits,
        "weighted_hits": coverage.weighted_hits,
        "last_seen_year": coverage.last_seen_year,
        "first_seen_year": coverage.first_seen_year,
        "inter_arrival_years_mean": coverage.inter_arrival_years_mean,
        "inter_arrival_years_max": coverage.inter_arrival_years_max,
        "saturation_index": coverage.saturation_index,
        "freshness_flag": coverage.freshness_flag,
        "predicted_score": coverage.predicted_score,
        "complications_seen": list(coverage.complications_seen),
        "complications_unseen": list(coverage.complications_unseen),
        "occurrences": [
            {
                "year": occ.year,
                "question_number": occ.question_number,
                "confidence": occ.confidence,
                "is_primary": occ.is_primary,
                "complications": list(occ.complications),
            }
            for occ in coverage.occurrences
        ],
        "warnings": list(coverage.warnings),
        "tier": coverage.tier,
        "tier_reasons": list(coverage.tier_reasons),
    }
