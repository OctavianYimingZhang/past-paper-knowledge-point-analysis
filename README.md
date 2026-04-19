# Past Paper Knowledge Point Analysis

Predictive, uncertainty-quantified analysis of MCQ past papers and lecture
material. The skill tells you how likely each course knowledge point is to
appear on the next exam, how confident that call is, and how much the
answer depends on modelling choices.

The skill was written for a University of Manchester School of Biological
Sciences student who observed that around 20 of every 50 MCQ items are
verbatim or near-verbatim repeats from older papers, and that certain
topics are tested nearly every year. A prior version of the skill
categorized topics with hard frequency cutoffs (greater than 75 percent
"Anchor", greater than 50 percent "Core"). That method ignored the tiny
sample size (four to ten papers), gave every paper equal weight regardless
of recency, and offered no way to express uncertainty. This rewrite fixes
all three.

## What is new

- Moment-matched Beta posterior per knowledge point with a 95 percent
  credible interval, recency-weighted by an exponential decay parameter
  `lambda`.
- A lecture-coverage regularization prior, strength capped at `tau` = 2,
  clearly labelled as a prior rather than empirical evidence.
- A split-halves bootstrap trend detector that replaces the
  underpowered Mann-Kendall approach.
- Tier rules that require posterior mean and credible-interval lower
  bound to clear joint thresholds, not a single frequency cutoff.
- A mandatory sensitivity sweep over `(lambda, tau)` plus a leave-one
  paper-out stability check. Unstable KPs surface at the top of every
  report.
- An orchestration layer that delegates stages of the pipeline to Haiku,
  Sonnet, and Opus subagents in Claude Code based on the judgment level
  each stage needs.

## How it works

1. Haiku subagents run mechanical extraction on papers, lectures, and
   answer keys.
2. A Sonnet subagent consolidates candidate topics into a final
   knowledge-point list and maps every question to one primary KP.
3. The pure-Python statistical core computes the posterior, credible
   interval, trend, and tier for every KP, plus the sensitivity sweep and
   leave-one-out analysis.
4. An Opus subagent interprets borderline or unstable results for the
   student in plain language.
5. Haiku assembles the final Markdown, merging the Opus narratives into
   the auto-generated report.

See `SKILL.md` for the orchestration contract and
`references/subagent-orchestration.md` for the prompt templates.

## Repository layout

```
past-paper-knowledge-point-analysis/
  SKILL.md
  README.md
  requirements.txt
  agents/
    ocr-extractor.md
    topic-mapper.md
    statistical-interpreter.md
  references/
    methodology.md
    tier-definitions.md
    subagent-orchestration.md
    course-spec-schema.md
    presets.md
    specs/
      example-manchester-biochem.json
  scripts/
    analyze_past_papers.py     # CLI entry point
    extract_papers.py
    extract_lectures.py
    extract_answer_keys.py
    statistical_model.py
    sensitivity.py
    report_writer.py
    vision_ocr.swift           # optional macOS OCR helper
  tests/
    test_statistical_model.py
    test_sensitivity.py
```

## Installation

Python 3.11 or newer is required.

```bash
pip install -r requirements.txt
```

## Run

The skill runs in stages. Each stage produces a JSON artifact in
`output_dir` that the next stage consumes.

```bash
# Stage 2: mechanical paper extraction
python3 -m scripts.analyze_past_papers extract-papers --spec path/to/spec.json

# Stage 3: lecture coverage
python3 -m scripts.analyze_past_papers extract-lectures --spec path/to/spec.json

# Stage 4: answer-key image dump and text parse (optional)
python3 -m scripts.analyze_past_papers extract-answer-keys --spec path/to/spec.json

# Stages 5 and 6 are delegated to a Sonnet subagent; they write mapping.json.

# Stage 7: Bayesian posterior, sensitivity sweep, and reports
python3 -m scripts.analyze_past_papers analyze --spec path/to/spec.json
```

## Outputs

In `output_dir`:

- `<course_id>-analysis.xlsx` with sheets `Method`,
  `Posterior_Predictions`, `Sensitivity_Sweep`, `Leave_One_Out`,
  `Trend_Analysis`, `Review_Queue`.
- `<course_id>-analysis.json` containing every posterior, every sweep
  cell, and every leave-one-out row. Sufficient to reproduce the Excel
  and Markdown deterministically.
- `<course_id>-analysis.md` with unstable KPs surfaced first, tier
  summary tables, and (once stage 8 runs) Opus-written narratives for
  borderline KPs.

## Tests

```bash
python3 -m pytest tests/ -q
```

The statistical core has full unit coverage: recency weighting, credible
interval bounds, prior construction, trend detection, tier assignment,
sensitivity sweep, and leave-one-out stability.

## Statistical contract

- Every probability is reported with a credible interval. A point
  estimate without its interval is a bug.
- Tier assignments must include a reasons list. A tier without reasons
  is a bug.
- The model is a moment-matched Beta approximation under recency
  weighting. It is not a strict conjugate posterior. The word
  "conjugate" must not appear in user-facing output.
- `lambda` is swept over `{0, 0.2, 0.4}` and `tau` over `{0.5, 1.0, 2.0}`
  by default. Results that flip tiers across the sweep are labelled
  unstable and surfaced first.

Full details in `references/methodology.md`.

## Licensing

Apache 2.0. See `LICENSE`.
