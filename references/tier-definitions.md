# Tier Definitions

The skill carries **two parallel tier systems** that the student should
read together but never confuse:

- The **KP tier** (`anchor / core / emerging / legacy / oneoff /
  not_tested`) lives on each knowledge point and answers *whether* a topic
  appears next sitting. It is decided from the moment-matched Beta
  posterior, the recency-weighted trend, and raw counts.
- The **pattern tier** (`saturated / hot / fresh / dormant`) lives on each
  `(KP, pattern)` cell and answers *how* a topic is likely to be tested.
  It is decided from frequency, recency, the saturation index, and the
  freshness flag — never a posterior, because pattern data is too sparse
  to support an honest credible interval.

Each tier assignment (KP or pattern) carries an ordered list of reasons so
the decision is auditable.

All KP-tier thresholds are stored in
`scripts/statistical_model.assign_tier`. All pattern-tier thresholds are
stored in `scripts/pattern_coverage.assign_pattern_tier`. Changing them
here without updating the corresponding function (and the snapshot tests)
is a specification bug.

## KP Tier Rules

The rules fire in the order listed. The first matching rule wins.

| Priority | Tier | Rule | Intended meaning |
|----------|------|------|------------------|
| 0 | `not_tested` | No exam evidence in any year | Curriculum-only inference; do not treat as a real prediction |
| 1 | `anchor` | `posterior_mean >= 0.75` AND `ci_lower_95 >= 0.50` | High-confidence recurring topic; core revision priority |
| 2 | `core` | `posterior_mean >= 0.50` AND `ci_lower_95 >= 0.25` | Probable recurrence with moderate uncertainty |
| 3 | `emerging` | `trend_label == "rising"` AND `posterior_mean >= 0.30` | Recently heating up; watch for further growth |
| 4 | `legacy` | `trend_label == "cooling"` AND historical rate >= 0.50 AND `posterior_mean < 0.40` | Used to be common, now fading; low revision priority unless a safety net is needed |
| 5 | `oneoff` | `raw_hits == 1` AND no stronger signal matched | Single appearance; uncertain about recurrence |
| 6 | `not_tested` | `raw_hits == 0` (falls through) | Zero exam hits across available years |
| 7 | `oneoff` (fallback) | `raw_hits >= 2` AND nothing else matched | Multiple hits but posterior evidence is weak; treat as low priority |

## Reasons Payload

Each KP output includes a `tier_reasons` tuple explaining which rule fired.
Examples:

- `("posterior_mean=0.83 >= 0.75", "ci_lower=0.55 >= 0.50")`
- `("trend=rising", "posterior_mean=0.37 >= 0.30")`
- `("no exam evidence; curriculum-only inference",)`

Reasons are not optional. Any output row without them is invalid.

## Anti-patterns

The following are explicitly not allowed:

1. Picking a tier from a single posterior point estimate without the
   credible interval condition. An `anchor` result that happens to have a
   `ci_lower_95` of 0.12 is a bug, not a tier.
2. Calling the retention cut "conjugate posterior" anywhere in user-facing
   output. The model uses a moment-matched Beta approximation; the copy
   must say so.
3. Smuggling recency weighting into the tier logic itself. Recency feeds
   into the posterior only; the tier rules read the resulting posterior.
4. Down-weighting the curriculum prior until the data wins every time.
   `tau` is capped at 2.0 and must be reported per row.
5. Treating `sensitivity_band = "unstable"` as a cosmetic flag. The
   Markdown summary must surface unstable KPs ahead of the tier tables.

## Worked Examples

These snapshots are exercised by `tests/test_statistical_model.py`.

### Anchor

Seven formal years, all hits, curriculum coverage 0.35, lambda 0.1,
tau 1.0. `posterior_mean` around 0.90, `ci_lower_95` around 0.65, trend
stable. Rule 1 fires. Reasons include the mean and CI thresholds.

### Core

Six papers, four hits, curriculum coverage 0.12, lambda 0.2, tau 1.0.
`posterior_mean` around 0.63, `ci_lower_95` around 0.28, trend stable. Rule
1 fails (mean below 0.75); rule 2 fires.

### Emerging

Eight papers, two hits in the last three years, zero in the first five,
curriculum coverage 0.08. Trend test returns "rising" because the bootstrap
interval is fully above zero. `posterior_mean` around 0.32. Rule 3 fires.

### Legacy

Eight papers, five hits concentrated in the earliest four years, zero hits
in the last three. Historical rate = 5/8 = 0.625. Trend test returns
"cooling". `posterior_mean` around 0.25 under moderate recency weighting.
Rule 4 fires.

### One-off

Five papers, one hit in 2020, all other years miss. `posterior_mean`
around 0.20, `ci_lower_95` around 0.02, trend stable. Rules 1-4 fail;
rule 5 fires with `raw_hits == 1`.

### Not tested

Zero papers available for the KP, curriculum coverage 0.40. Rule 0 fires
immediately. `posterior_mean` is prior-driven; warning records
"curriculum-only inference".

## Pattern Tier Rules

The pattern tier decorates each `(kp_id, pattern_id)` cell with one of
`saturated`, `hot`, `fresh`, or `dormant`. The rules fire in priority
order; the first matching rule wins. Pattern tiers are orthogonal to KP
tiers — a `not_tested` KP can host a `fresh` pattern (the textbook seeds
the pattern, the examiner has not used it), and an `anchor` KP can host
both `saturated` and `fresh` patterns at once.

| Priority | Tier | Rule | Intended meaning |
|----------|------|------|------------------|
| 0 | `saturated` | `saturation_index >= 0.6` AND `raw_hits >= 2` | Examiner has been recycling this pattern in adjacent or near-adjacent sittings; downweight predicted score, drill once for safety, then move on |
| 1 | `hot` | `predicted_score >= median(predicted_score for KP) * 1.25` AND `raw_hits >= 2` AND not `saturated` | Bread-and-butter pattern: regular hits, varied recently, primary drill target |
| 2 | `fresh` | `freshness_flag == True` | Seeded by textbook or lecture, unseen for `fresh_gap_years` (default 4) or never used; asymmetric upside, prepare 1–2 worked examples |
| 3 | `dormant` | otherwise | Either zero hits with no material seed, or last seen long ago without being seeded — low revision priority unless the student has spare time |

### Worked examples — pattern layer

- **Saturated.** `L13.03.P02` (tangent at named point on implicit curve) —
  hits in 2021, 2022, 2023, 2024. `saturation_index = 0.78`,
  `weighted_hits = 3.7`. Tier `saturated`. Reasons:
  `("saturation_index=0.78 >= 0.6", "raw_hits=4 >= 2")`. Narrative phrase:
  "examiner is recycling — drill once and move on".
- **Hot.** `L02.03.P01` (closest approach of two ships) — hits in 2017,
  2019, 2022, 2024 with full prompt variation. `saturation_index = 0.31`,
  `predicted_score = 1.4 * KP_median`. Tier `hot`. Reasons:
  `("predicted_score=2.1 >= 1.5", "raw_hits=4 >= 2",
    "saturation_index=0.31 < 0.6")`.
- **Fresh.** `L13.03.P05` (vertical-tangent edge case) — `raw_hits = 0`,
  cited in textbook §5.4 example 14. Tier `fresh`. Reasons:
  `("freshness_flag=True", "seeded by textbook §5.4 example 14")`.
- **Dormant.** `L08.01.P03` (binomial expansion when `n` is irrational) —
  unseen, unseeded by textbook for this unit. Tier `dormant`. Reasons:
  `("raw_hits=0", "freshness_flag=False")`.

## Anti-patterns — pattern layer

The following are explicitly not allowed in the pattern layer:

1. Reporting a Beta posterior or credible interval at the pattern level.
   With `n_eff` of 0–5, any interval is honestly uninformative. Use
   frequency + saturation + freshness wording instead.
2. Calling a `fresh` pattern "low probability". Freshness is an asymmetric
   upside, not a frequency claim. The examiner has not yet picked it up;
   that says nothing about whether they will next sitting.
3. Inventing pattern_ids in the mapping output. The `pattern-architect`
   agent owns the taxonomy; the `pattern-classifier` agent must use ids
   that already exist in `patterns.json` and surface mismatches in the
   review queue.
4. Collapsing predicted_score, saturation_index, and freshness_flag into a
   single ranking number. Each surface answers a different question; the
   DOCX report carries them as parallel columns.
