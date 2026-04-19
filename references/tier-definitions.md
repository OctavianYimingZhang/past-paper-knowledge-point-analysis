# Tier Definitions

Tiers replace the old `Anchor / Core / Recurring / One-off / Not tested`
bands. Each tier is defined by rules on the Bayesian posterior, the trend
signal, and the raw counts. Every tier assignment carries an ordered list
of reasons so the decision is auditable.

All thresholds are stored in `scripts/statistical_model.assign_tier`.
Changing them here without updating the function (and the snapshot tests)
is a specification bug.

## Tier Rules

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
