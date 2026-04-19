# Methodology

This document explains how the skill turns past papers and lecture materials
into a predictive, uncertainty-quantified knowledge-point model. It is the
source of truth for the statistical contract enforced by the code and the
SKILL.md orchestration rules.

## Problem Statement

A student has:

- Lecture slides or lecture-note PDFs for a course.
- A small number of past papers (typically 4 to 10 years), each containing
  25 to 50 multiple-choice questions.
- Optional answer keys that sit alongside those papers.

The student wants to know, for every knowledge point taught in the course:

1. How likely is this topic to appear on the next exam?
2. How confident can we be in that estimate given the tiny sample size?
3. Is the topic trending up, stable, or cooling off year to year?
4. How much weight does the answer depend on modelling choices?

The prior version of this skill answered (1) with a raw frequency and
bucketed it with hard cutoffs (greater than 75 percent equals "Anchor",
greater than 50 percent equals "Core"). That approach ignored uncertainty,
conflated recent and ancient evidence, and left the student with no way to
tell a durable topic from one that happened to clear a threshold on a noisy
cohort. The redesign replaces that machinery with an explicit Bayesian
model and three layers of sensitivity analysis.

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
