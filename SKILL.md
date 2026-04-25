---
name: past-paper-knowledge-point-analysis
description: Material-first, pattern-aware analysis of past papers. Reads textbook and lecture material to derive the universe of question patterns per knowledge point, maps each past-paper question to its KP and pattern, then runs a moment-matched Beta posterior at the KP level and transparent frequency / saturation / freshness statistics at the pattern level. Predicts not only which topics will appear but how (which pattern), with solution sketches and "already tested" vs "still possible" decompositions. Works for MCQ, short-answer, and structured exams. Outputs DOCX, XLSX, Markdown, and JSON. Use when the user wants to know which topics and which question styles are likely to appear next sitting and how confident that call is.
---

# Past-Paper Knowledge-Point and Pattern Analysis

## What this skill produces

The pipeline runs in two layers.

**KP layer** — for every knowledge point (KP) defined by the lecture and
textbook material, the skill outputs:

- A moment-matched Beta posterior over "the topic appears next sitting"
  with a 95 percent credible interval.
- A tier assignment (`anchor`, `core`, `emerging`, `legacy`, `oneoff`,
  `not_tested`) decided by rules on that posterior, not on hard cutoffs.
  Every tier carries an auditable `tier_reasons` list.
- A split-halves bootstrap trend label (`rising`, `cooling`, `stable`,
  `insufficient`).
- Per-paper hotness (mean and standard deviation, normalised to paper size).
- A `sensitivity_band` of `stable` or `unstable` from a (lambda, tau)
  grid sweep, a leave-one-paper-out check, and a `warnings` field.

**Pattern layer** — for every (KP, pattern) cell, the skill outputs:

- Raw and recency-weighted hit counts.
- Last-seen and first-seen years; inter-arrival statistics.
- A `saturation_index` in [0, 1] combining recent density and reuse-cluster
  detection — high values mean the examiner has been recycling.
- A `freshness_flag` for textbook/lecture-seeded patterns the examiner has
  not used in `fresh_gap_years` (default 4 years) — these are the
  asymmetric upside of revision time.
- A `predicted_score` combining frequency, recency, and a tunable novelty
  bias `alpha` (default 0.3).
- `complications_seen` vs `complications_unseen` lists per pattern.

Pattern-level outputs do NOT carry credible intervals: with typical n_eff
of 0–5 hits per cell, a Beta posterior would be uselessly wide. The pattern
layer is honest frequency + recency + freshness, no more.

Never produce a retention number without its credible interval. Never call
the KP posterior "conjugate"; it is a moment-matched Beta approximation,
as documented in `references/methodology.md`.

## When to invoke this skill

The user has:

- Lecture slides and / or a consolidated lecture-notes PDF.
- A textbook PDF aligned to the same syllabus (strongly recommended — it
  seeds the pattern taxonomy for each KP). When absent, the skill still
  produces patterns from lectures only and marks each pattern's source
  accordingly.
- Three or more past papers of the same course. MCQ, short-answer, and
  structured papers are all supported by the relaxed parser.
- Optional DOCX answer keys.

They want:

- Predictions that name **what** topics will appear AND **how** they will
  be tested (which pattern, what setup, what solution path).
- Distinction between heavily reused ("saturated") patterns and
  textbook-seeded but unseen ("fresh") patterns.
- Auditable uncertainty quantification at the KP level.
- Sensitivity checks and data warnings so the student knows where the
  evidence is thin.

If any required input is absent, pause and ask rather than guess.

## Pipeline (10 stages)

Some stages are mechanical, some require semantic judgment, some are pure
math. Pick the model for each stage by the rules below. Use the `Task`
tool with an explicit `model` parameter where indicated. See
`references/subagent-orchestration.md` for ready-to-paste prompt templates.

| Stage | Task | Model | Notes |
|-------|------|-------|-------|
| 1. Spec audit | Read the spec JSON, validate paths, list missing sources | Main Claude | No subagent |
| 2. Paper extraction | `python3 -m scripts.analyze_past_papers extract-papers --spec <spec>` then review warnings | **Haiku 4.5** | Multi-paper review can be parallel. Parser auto-detects MCQ vs short-answer. |
| 3. Lecture extraction | `extract-lectures` then review coverage shares | **Haiku 4.5** | Mechanical |
| 3b. Textbook extraction | `extract-textbook` to capture chapter index + worked examples | **Haiku 4.5** | NEW. Skip if no textbook PDF supplied. |
| 4. Answer-key OCR | `extract-answer-keys`, then OCR dumped images | **Haiku 4.5** | Vision required. Skip if no DOCX answer keys. |
| 5. KP boundary optimisation | Consolidate candidate topics into the canonical KP list (`kps.json`) | **Sonnet 4.6** (`agents/topic-mapper.md`) | Semantic judgment |
| 5b. Pattern taxonomy derivation | Read `kps.json` + `extracted-lectures.json` + `extracted-textbook.json`; emit `patterns.json` | **Sonnet 4.6** (`agents/pattern-architect.md`) | NEW. Every pattern MUST cite a source. |
| 6. Question-to-KP-pattern mapping | Tag each question with `(primary_kp, pattern_id, alt_pattern_ids, prompt_summary, asked_operation, complications, marks, confidence)` | **Sonnet 4.6** (`agents/pattern-classifier.md`) | NEW. Confidence < 0.7 flags for review. |
| 7. Statistical analysis | `python3 -m scripts.analyze_past_papers pattern-coverage --spec <spec>` then `analyze --spec <spec>` | Pure Python | No LLM. The CLI runs both KP-level Beta posterior and pattern-level coverage statistics. |
| 8. Tier and pattern interpretation | Per-KP narratives with pattern decomposition, "already tested" lists, "still possible" lists, drill set | **Opus 4.7** (`agents/statistical-interpreter.md`) | High-judgment, small batch |
| 9. Report assembly | Render Markdown, XLSX, and DOCX from the JSON payloads + Opus narratives | **Haiku 4.5** | Already wired into `cmd_analyze`; this stage is mostly verifying. |

The statistical stage MUST NOT be delegated to an LLM. KP-level Bayesian
math and pattern-level coverage math are pure Python function calls. If the
orchestrator catches itself asking a subagent to do statistics, stop and
run the CLI instead.

## Contract for every user-facing summary

Any summary, Markdown, DOCX, or Opus narrative MUST:

- Attach a credible interval to every KP-level probability.
- Quote `lambda`, `tau`, `alpha`, and `reference_year` up front.
- Mark unstable KPs before the tier tables.
- Use `moment-matched Beta posterior` wording for the KP layer; never
  `conjugate posterior`.
- Use `frequency + saturation + freshness` wording for the pattern layer;
  never claim a credible interval at the pattern level.
- Preserve the tier reasons list (do not paraphrase them away).
- Call out any KP with a non-empty warnings list.
- For every anchor / core KP, the narrative must decompose into pattern
  language: dominant pattern, saturated pattern(s), fresh pattern(s) when
  any are flagged.

## Required files

- `references/methodology.md` is the statistical source of truth.
- `references/tier-definitions.md` names every tier rule and the parallel
  pattern tier (`saturated`, `hot`, `fresh`, `dormant`).
- `references/course-spec-schema.md` describes the input JSON.
- `references/presets.md` enumerates known courses (Manchester Y1 biology
  and Edexcel IAL Maths units).
- `references/subagent-orchestration.md` lists the prompt templates per
  stage.

## How to run end-to-end

1. Confirm the spec with the user; resolve any missing sources. Ask for the
   textbook PDF if the syllabus has one and it is not in the spec.
2. Delegate stage 2 (`extract-papers`) to a Haiku subagent.
3. Delegate stage 3 (`extract-lectures`) to a Haiku subagent.
4. Delegate stage 3b (`extract-textbook`) to a Haiku subagent if a
   textbook PDF is supplied.
5. Delegate stage 4 (`extract-answer-keys`) to a Haiku subagent if DOCX
   answer keys are present.
6. Delegate stage 5 (KP boundaries) to a Sonnet subagent. The subagent
   writes `kps.json`.
7. Delegate stage 5b (pattern taxonomy) to a Sonnet subagent following
   `agents/pattern-architect.md`. The subagent writes `patterns.json`.
8. Delegate stage 6 (mapping) to a Sonnet subagent following
   `agents/pattern-classifier.md`. The subagent writes `mapping.json` with
   schema_version 2 (pattern_ids, prompt_summary, etc.).
9. Run `python3 -m scripts.analyze_past_papers pattern-coverage --spec
   <spec>` to produce `pattern-coverage.json`.
10. Run `python3 -m scripts.analyze_past_papers analyze --spec <spec>` to
    produce KP-level posteriors, sensitivity sweeps, and the four output
    files (`<course_id>-analysis.{json,xlsx,md,docx}`).
11. Delegate stage 8 (tier + pattern narratives) to an Opus subagent,
    feeding only the relevant slice of the JSON payload + pattern coverage.
12. Re-run `analyze` so the DOCX picks up `tier-narratives.json` (the
    writer reads it best-effort).
13. Hand the user the DOCX (the revision-plan deliverable), the Excel
    workbook, the Markdown summary, and a short operator note listing any
    open `Review_Queue` items.

## What not to do

- Do not run the full skill in a single long Claude turn. Delegate the
  mechanical and semantic work so the main context stays free for the
  high-judgment stage 8.
- Do not invent pattern_ids that are not in `patterns.json`. The
  `pattern-architect` agent owns the taxonomy.
- Do not claim a credible interval at the pattern level. The data is too
  sparse to support one honestly.
- Do not collapse hotness, P(appearance), saturation, and predicted_score
  into one ranking score.
- Do not silently ignore `sensitivity_band=unstable` KPs. They surface
  first in every summary.
- Do not assert a question-level repeat probability outside the pattern
  framework. The skill predicts at the KP and pattern levels by design.

## Run

```bash
# Mechanical extraction
python3 -m scripts.analyze_past_papers extract-papers   --spec spec.json
python3 -m scripts.analyze_past_papers extract-lectures --spec spec.json
python3 -m scripts.analyze_past_papers extract-textbook --spec spec.json
python3 -m scripts.analyze_past_papers extract-answer-keys --spec spec.json

# Sonnet subagents write kps.json, patterns.json, mapping.json into the
# output directory.

# Pure-Python statistics
python3 -m scripts.analyze_past_papers pattern-coverage --spec spec.json
python3 -m scripts.analyze_past_papers analyze         --spec spec.json
```

The default report language is English. To produce bilingual or
Chinese-only output, pass `--lang both` or `--lang zh` to `analyze`.
