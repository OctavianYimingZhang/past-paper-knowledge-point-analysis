# Methodology

This document explains how the skill turns past papers and lecture materials
into a predictive, uncertainty-quantified knowledge-point model. It is the
source of truth for the statistical contract enforced by the code and the
SKILL.md orchestration rules.

## Problem Statement

A student has:

- Lecture slides or lecture-note PDFs for a course.
- Optionally a textbook PDF aligned to the same syllabus.
- A small number of past papers (typically 4 to 28 years). Papers may be
  multiple choice, short answer, or fully structured. Each paper contains
  10 to 50 questions, each carrying 1 to 15 marks.
- Optional answer keys (DOCX with marker-scheme images) alongside those
  papers.

The student wants to know, for every knowledge point taught in the course:

1. How likely is this topic to appear on the next exam?
2. How confident can we be in that estimate given the tiny sample size?
3. Is the topic trending up, stable, or cooling off year to year?
4. How much weight does the answer depend on modelling choices?
5. **If the topic appears, how is it likely to be tested** — which
   *question pattern* (setup, given objects, asked operation, answer type)?
6. **What patterns are still possible but unseen recently**, and which
   patterns has the examiner saturated?

The prior version of this skill answered (1) with a raw frequency and
bucketed it with hard cutoffs (greater than 75 percent equals "Anchor",
greater than 50 percent equals "Core"). That approach ignored uncertainty,
conflated recent and ancient evidence, and left the student with no way to
tell a durable topic from one that happened to clear a threshold on a noisy
cohort. The redesign replaces that machinery with an explicit Bayesian
model and three layers of sensitivity analysis.

Questions (5) and (6) are addressed by the **pattern layer** introduced
alongside the KP layer. The KP layer answers *whether* a topic appears; the
pattern layer answers *how*. The two layers are produced from the same
mapping pipeline but use different statistics — see "Pattern Layer" below.

## Modelling Choices

### Why a moment-matched Beta posterior

For each knowledge point (KP) the per-year outcome is a Bernoulli trial:
either the topic appeared on the paper or it did not. With four to ten
trials we cannot afford a multi-parameter model. A Beta-Binomial-style
posterior is the natural fit. It yields a full distribution, it produces
credible intervals for free, and it composes well with a weakly informative
prior derived from lecture coverage.

The wrinkle is that we apply a real-valued recency weight to each trial.
Strict Beta-Binomial conjugacy assumes integer trials. Replacing counts
with fractional weighted sums breaks the conjugacy. We therefore call the
output a *moment-matched Beta posterior*: a Beta distribution fitted to the
first two moments of the weighted likelihood. The skill never labels the
output as a "conjugate posterior"; every report sheet carries the
hyperparameters so the approximation can be audited.

### Why not logistic regression, IRT, or Mann-Kendall

- Logistic regression burns degrees of freedom instantly when the sample is
  four to ten papers with one topic-specific feature per KP. The odds
  ratios are not interpretable at that size.
- Item Response Theory models student ability against item difficulty. It
  is not the right tool for *item recurrence* across years.
- The Mann-Kendall trend test needs at least eight observations for even
  marginal power at the usual significance level. At five to seven papers
  it accepts the null too often to be useful. We replace it with a
  split-halves bootstrap on the difference of empirical rates.

### Why recency weighting, and how to pick lambda

The Manchester syllabus evolves year to year. A topic that appeared in 2016
is less predictive of 2025 than a topic that appeared in 2024. Exponential
decay with a single parameter `lambda` is the simplest defensible form:

```text
w_i = exp(-lambda * (reference_year - year_i))
```

We do not pick a single lambda. The skill sweeps `lambda` across
`{0.0, 0.2, 0.4}` and reports how the tier decision moves. A KP that stays
in the same tier across all three lambdas is a durable call. A KP that
flips between tiers is flagged `sensitivity_band = "unstable"` and the
Markdown summary surfaces it at the top of the review queue.

### Why a curriculum prior, bounded to tau <= 2

Treating lecture coverage as Bayesian evidence is tempting and dangerous.
"Slides devote X percent of their pages to topic K, therefore prior mean
equals X percent" smuggles the unverified assumption that slide share
predicts exam share. We mitigate this two ways:

1. The prior strength `tau` is capped at 2.0 and defaults to 1.0, labelled
   explicitly as a *regularization prior* rather than an empirical one.
2. The skill runs a sensitivity sweep over `tau` as well so a reader can
   see how much the result depends on the prior.

`tau = 0` disables the curriculum signal entirely and falls back to a
Beta(1, 1) uniform prior. `tau = 2` is the ceiling and behaves like "two
pseudo-papers of evidence". Anything stronger is not accepted.

### Why split-halves bootstrap for trend detection

With four to ten papers, any test that assumes asymptotic distributions
under-covers. A non-parametric bootstrap of the rate difference between
the older and newer halves of the data needs no asymptotics and yields a
direct credible interval on the trend delta. We label the topic "rising"
only when the entire 95 percent interval is above zero, and "cooling" only
when the entire interval is below zero. Everything else is "stable" or
"insufficient" (for fewer than four papers).

### Why hotness is kept separate from P(appearance)

"How often is this topic tested" and "how much of each paper is this topic
worth" are two questions. The first is a binary appearance rate. The
second is a share of paper content. Papers vary in length from 25 to 50
questions; collapsing both into one score mishandles short papers.

The skill reports `posterior_mean` and credible interval for (1) and
`hotness_mean_share` plus `hotness_std_share` for (2). They are two
columns in the output, never multiplied together.

## Required Sensitivity Analyses

Every run emits three stability views and stores them in the Excel
workbook alongside the primary predictions:

1. **lambda x tau sweep.** Re-run the analysis across a three-by-three
   grid. Record the tier at every cell. Attach a `sensitivity_band` of
   "stable" when one tier wins the grid, "unstable" otherwise.
2. **Leave-one-paper-out.** Drop each paper in turn and recompute the
   posterior. Report the maximum absolute shift in `posterior_mean` and
   list any years whose removal flipped the tier.
3. **Warning flags.** Every row carries a warnings field that surfaces
   known weak spots. Examples: `effective_N < 2`, mixed syllabus versions,
   no coverage signal, single-paper evidence.

## Failure Modes and Mitigations

| Failure | Signal | Mitigation |
|---------|--------|------------|
| Topic appears in lectures but was never tested | `raw_hits=0`, `coverage_share>0` | Tier is `not_tested` with explicit "curriculum inference, no exam evidence" warning. Prior strength capped at tau <= 2. |
| A single 2025 hit inflates the posterior under aggressive recency | `effective_N < 2` with lambda = 0.4 | Warning emitted. Sensitivity sweep exposes tier instability. |
| Syllabus change year mixed with older papers | `syllabus_version` differs across observations | Warning emitted. Spec author may set `weight_override` on the affected paper to down-weight it. |
| Answer key is image-only and OCR is weak | Paper cannot be segmented cleanly | Review queue surfaces the affected year; the KP is dropped from posterior math for that year rather than guessed. |
| Very few papers overall | `n_papers <= 3` | Trend becomes `insufficient`; bootstrap shrinks; warning emitted. |

## Output Contract

Every KP row exported by the pipeline carries these fields:

- Identifiers: `kp_id`, `lecture_id`, `optimized_topic`.
- Hyperparameters: `lambda_used`, `tau_used`, `reference_year`.
- Raw counts: `n_papers`, `raw_hits`.
- Weighted evidence: `weighted_hits`, `weighted_N`.
- Prior: `coverage_share`, `prior_alpha`, `prior_beta`.
- Posterior: `posterior_alpha`, `posterior_beta`, `posterior_mean`,
  `ci_lower_95`, `ci_upper_95`.
- Hotness: `hotness_mean_share`, `hotness_std_share`.
- Trend: `trend_label`, `trend_delta`, `trend_ci_95`.
- Decision: `tier`, `tier_reasons`.
- Stability: `sensitivity_band`, `warnings`.

A summary that omits any of these fields is not compliant with the
methodology. SKILL.md enforces this contract on any subagent writing the
final Markdown or Excel summary.

## Pattern Layer

The KP layer predicts *whether* a topic appears next sitting. The pattern
layer predicts *how*. The student then sees not just "implicit
differentiation will likely appear (posterior 0.81 [0.41, 1.00])" but also
"the most likely pattern is L03.02.P02 — find the tangent line at a named
point on an implicit curve, which has been used in 5 of the last 7 papers
and is saturating; pattern L03.02.P05 (vertical-tangent edge case) is fresh
in the textbook but has not appeared since 2018".

### Where patterns come from

Patterns are derived from **course material first**, papers second. The
`pattern-architect` Sonnet 4.6 subagent reads:

- `kps.json` — the canonical knowledge-point list.
- `extracted-textbook.json` — chapter index, worked examples, end-of-chapter
  exercises (textbook is the seed because it describes the *full* universe
  of how a KP can be tested, not just what the examiner has used).
- `extracted-lectures.json` — lecture bullet contexts that signal worked
  examples ("Example", "e.g.", "Exercise").

The agent emits `patterns.json`. Each pattern entry carries `kp_id`,
`pattern_id`, `label`, `description`, `given_objects`, `asked_operation`,
`answer_type`, `skills_invoked`, `solution_sketch` (ordered list),
`common_complications`, and a non-empty `source` list citing the textbook
section or lecture slide that justified the pattern. Patterns invented
without citation are rejected.

The `pattern-classifier` Sonnet 4.6 subagent then maps each past-paper
question to:

- exactly one `primary_kp` and up to two `secondary_kps`,
- exactly one `pattern_id` (must exist in `patterns.json`),
- up to two `alt_pattern_ids` with explicit confidences in `(0, 1]`,
- structured metadata: `prompt_summary`, `given_objects`, `asked_operation`,
  `answer_type`, `key_steps_observed`, `complications`, `marks`,
  `confidence`.

### Pattern statistics — frequency, recency, and freshness

Pattern data is sparse. A typical `(KP, pattern)` cell sees 0–5 hits across
11–28 papers. A Beta posterior would be uselessly wide:
Beta(1+0.4, 1+27.6) yields a 95 percent credible interval roughly
[0.001, 0.10] regardless of which fresh pattern you ask about. The model
would carry numbers but no information.

We therefore use transparent frequency statistics with explicit recency and
freshness signals. **No credible interval is reported at the pattern
level.** The skill's contract uses the wording *frequency + saturation +
freshness* for the pattern layer and reserves *moment-matched Beta
posterior* for the KP layer.

Per `(kp_id, pattern_id)` cell, with `lambda` shared with the KP layer:

```text
raw_hits         = count of papers where this pattern was the primary
                   (alternate hits weighted at 0.5 * confidence)
weighted_hits    = sum_i exp(-lambda * (reference_year - year_i)) * weight_i
last_seen_year   = max(year_i) over hits, or null
first_seen_year  = min(year_i) over hits, or null
inter_arrival    = mean / max gap between consecutive hits in years
```

The **saturation index** captures "the examiner has been recycling this
pattern recently". It combines a recent-density term and a reuse-cluster
term, both squashed into `[0, 1)`:

```text
recent_density  = (weighted_hits restricted to ref_year - 3 <= year_i)
                  / max(2.0, weighted_N_recent)
cluster_term    = number_of_consecutive_pairs_within_2_years / max(1, raw_hits)
saturation_idx  = 1 - exp(-(recent_density + 0.5 * cluster_term))
```

A saturation index near 0 means "rarely used or only used long ago". A
saturation index near 1 means "the examiner has reused this pattern in
adjacent sittings". Saturated patterns get a small downweight in the
predicted score because the examiner is more likely to vary, and the
student has more representative drilling material already available.

The **freshness flag** identifies patterns the syllabus *enables* but the
examiner has not used recently:

```text
freshness_flag  = (pattern is seeded by textbook OR lecture)
                  AND (raw_hits == 0 OR last_seen_year < ref_year - fresh_gap_years)
```

`fresh_gap_years` defaults to 4. Fresh patterns are the asymmetric upside
of revision time: they cost little to prepare against, and if the examiner
picks one up next sitting, the student is the only one ready.

The **predicted score** combines the three signals through a tunable
novelty bias `alpha` (default `0.3`):

```text
predicted_score = weighted_hits * (1 - alpha * saturation_idx)
                + alpha * 0.5 if freshness_flag else 0
```

`alpha = 0` reduces the system to pure recency-weighted frequency.
`alpha > 0` discounts saturated patterns and rewards textbook-seeded but
unused patterns. The CLI exposes `alpha` so the user can override it.

### Why no Beta posterior at the pattern level

Three reasons:

1. **Sample size.** `n_eff` per cell is typically 0–5. A Beta posterior
   would carry an interval so wide that any tier decision based on it is
   noise. The KP layer survives with `n_eff` of 4–28; the pattern layer
   would not.
2. **Definition stability.** A pattern is a human-named taxonomy; merging
   two near-duplicate patterns can move the count from 1 to 2 without any
   change in evidence. Bayesian inference assumes a fixed event space.
   Frequency + recency + freshness degrade gracefully under taxonomy
   tweaks; a posterior would not.
3. **Honesty.** The student should see "this pattern has been used in the
   last 3 of 4 sittings — saturated" instead of "P(pattern) = 0.62 [0.18,
   0.93] — anchor". The first is auditable; the second imports false
   precision.

The pattern layer is honest frequency, no more. Anyone porting the skill
must preserve this distinction — saturation is not a probability.

### Multi-pattern and multi-KP questions

A question that genuinely splits across two patterns of the *same* KP
records:

- the dominant pattern as `pattern_id` (full weight)
- the secondary pattern in `alt_pattern_ids` with explicit confidence,
  contributing `0.5 * confidence` to that pattern's hit weight

A question that genuinely uses two KPs records the dominant KP as
`primary_kp` and the secondary in `secondary_kps`. The KP-level statistics
count primary KPs only; secondary memberships surface in the narrative for
the student but do not double-count for tier decisions.

### Pattern-tier glossary

The pattern layer uses its own tiers, orthogonal to the KP-tier system.
See `references/tier-definitions.md` for the rules:

- `saturated` — high recent density and reuse cluster; downweight.
- `hot` — appeared frequently but not in adjacent sittings; bread-and-butter
  drill target.
- `fresh` — seeded by material, unseen or stale; asymmetric upside.
- `dormant` — seen long ago, no recent reuse, no freshness flag.

## Output Contract — Pattern Layer

Every `(kp_id, pattern_id)` row exported by `pattern-coverage.json`
carries:

- Identifiers: `kp_id`, `pattern_id`.
- Hyperparameters: `lambda_used`, `alpha_used`, `fresh_gap_years`,
  `reference_year`.
- Counts: `raw_hits`, `weighted_hits`.
- Recency: `last_seen_year`, `first_seen_year`,
  `inter_arrival_years_mean`, `inter_arrival_years_max`.
- Saturation and freshness: `saturation_index`, `freshness_flag`,
  `predicted_score`.
- Coverage: `complications_seen`, `complications_unseen`.
- Provenance: `occurrences` (list of `{year, question_number, confidence,
  is_primary, complications}`).
- Stability: `warnings`.

A pattern-level summary that imports KP-level wording ("conjugate
posterior", "credible interval") is not compliant with the methodology.

## Prior Art

- Agarwal and Chen (2011) on time-decayed Bayesian click-through-rate
  models motivated the recency-weighted Beta posterior.
- Kleinberg (2002) on burst detection is the canonical reference for
  trending signals in discrete event streams; we take the framing of
  "older half versus newer half" from that tradition.
- Anderson and Krathwohl (2001) revised Bloom taxonomy is relevant if the
  spec later wants to weight tiers by cognitive level.
- Item Response Theory (Lord, 1980) is deliberately NOT used because it
  models student ability against item difficulty, which is orthogonal to
  the "item recurrence across years" question this skill answers.
