---
name: past-paper-knowledge-point-analysis
description: Predictive, uncertainty-quantified analysis of MCQ past papers and lecture material. Produces per-knowledge-point posterior probability, credible intervals, recency-weighted trend, tier assignments with auditable reasons, and sensitivity sweeps. Use when the user wants to know which exam topics are likely to recur and how confident that call is. The skill orchestrates Claude Code subagents across Haiku, Sonnet, and Opus and invokes a pure-Python statistical core.
---

# Past Paper Knowledge Point Analysis

## What this skill produces

For every knowledge point (KP) defined by the lecture material, the skill
outputs:

- A moment-matched Beta posterior over "the topic appears on the next exam"
  with a 95 percent credible interval.
- A tier assignment (`anchor`, `core`, `emerging`, `legacy`, `oneoff`,
  `not_tested`) decided by rules on that posterior, not on hard 50/75
  cutoffs. Every tier carries a `tier_reasons` list.
- A split-halves bootstrap trend label (`rising`, `cooling`, `stable`,
  `insufficient`).
- A hotness mean and standard deviation expressed as a fraction of each
  paper so 25-question and 50-question exams are normalized.
- A `sensitivity_band` of `stable` or `unstable` from a lambda x tau grid
  sweep, a leave-one-paper-out stability analysis, and a `warnings` field
  that surfaces every known weak signal.

Never produce a retention number without its credible interval. Never call
the posterior "conjugate"; it is a moment-matched Beta approximation, as
explained in `references/methodology.md`.

## When to invoke this skill

The user has:

- Lecture slides or a consolidated lecture-notes PDF for a course.
- Between three and ten past papers of the same course.
- Optional DOCX answer keys.

They want:

- Ranking topics by probability of appearing on the next exam.
- Uncertainty quantification around that probability.
- Separation of durable topics from one-off topics and from emerging topics.
- Sensitivity checks so the student knows when the data is too thin to act on.

If any of the above is absent, pause and ask rather than guess.

## Subagent orchestration (read this before delegating)

The skill runs nine stages. Some are mechanical, some require semantics,
some are pure math. Pick the model for each stage by the rules below.
Use the `Task` tool with an explicit `model` parameter where indicated.
See `references/subagent-orchestration.md` for ready-to-paste prompt
templates.

| Stage | Task | Model | Notes |
|-------|------|-------|-------|
| 1. Spec audit | Read the spec JSON, validate paths, list missing sources | Main Claude | No subagent |
| 2. Paper extraction | Run `python3 -m scripts.analyze_past_papers extract-papers --spec <spec>` then review warnings | **Haiku 4.5** | Delegate via Task. Multiple papers can be reviewed in parallel |
| 3. Lecture extraction | Run `extract-lectures`, write coverage.json | **Haiku 4.5** | Delegate |
| 4. Answer-key OCR | Run `extract-answer-keys`, then OCR the dumped images | **Haiku 4.5** | Vision required |
| 5. KP boundary optimization | Consolidate candidate topics into final KP list | **Sonnet 4.6** | Semantic judgment |
| 6. Question-to-KP mapping | Assign primary and secondary KP to each question, write `mapping.json` | **Sonnet 4.6** | Emit per-question confidence |
| 7. Statistical analysis | Run `python3 -m scripts.analyze_past_papers analyze --spec <spec>` | Pure Python | No LLM |
| 8. Tier interpretation | Write rationale for borderline KPs, highlight `sensitivity_band=unstable`, explain tier flips | **Opus 4.7** | High-judgment, small batch |
| 9. Report assembly | Render the Markdown summary from the JSON payload and Opus narratives | **Haiku 4.5** | Template fill |

The statistical stage must not be delegated to an LLM. It is a pure Python
function call. If the orchestrator catches itself asking a subagent to do
Bayesian math, stop and run the CLI instead.

## Contract for every user-facing summary

Any summary, Markdown report, or Opus narrative MUST:

- Attach a credible interval to every probability.
- State `lambda`, `tau`, and `reference_year` up front.
- Mark unstable KPs before the tier tables.
- Use `moment-matched Beta posterior` wording, never `conjugate posterior`.
- Preserve the tier reasons list (do not paraphrase them away).
- Call out any KP with a non-empty warnings list.

## Required files

- `references/methodology.md` is the statistical source of truth.
- `references/tier-definitions.md` names every tier rule.
- `references/course-spec-schema.md` describes the input JSON.
- `references/presets.md` enumerates known courses.
- `references/subagent-orchestration.md` lists the prompt templates.

## How to run end-to-end

1. Confirm the spec with the user; resolve any missing sources.
2. Delegate stage 2 (`extract-papers`) to a Haiku subagent.
3. Delegate stage 3 (`extract-lectures`) to a Haiku subagent.
4. Delegate stage 4 (`extract-answer-keys`) to a Haiku subagent if DOCX
   answer keys are present.
5. Delegate stage 5 (KP boundary optimization) to a Sonnet subagent. Save
   the resulting KP list to the output directory.
6. Delegate stage 6 (question-to-KP mapping) to a Sonnet subagent. The
   subagent writes `mapping.json` to the output directory.
7. Run stage 7 (`analyze`) as a local Python CLI call.
8. Delegate stage 8 (tier narrative) to an Opus subagent, feeding only
   the relevant slice of the JSON payload.
9. Delegate stage 9 (report assembly) to a Haiku subagent.
10. Hand the user the Excel workbook, JSON payload, Markdown summary, and
    a short operator note listing any open `Review_Queue` items.

## What not to do

- Do not run the full skill with a single long Claude turn. Delegate the
  mechanical work so the main context stays free for stage 8 judgment.
- Do not invent tier thresholds. The rules in `tier-definitions.md` are
  the contract.
- Do not collapse hotness and P(appearance) into one score.
- Do not silently ignore `sensitivity_band=unstable` KPs. They must be
  surfaced first in every summary.
- Do not assert about question-level repeat probabilities. The skill is
  KP-level by design.

## Run

```bash
python3 -m scripts.analyze_past_papers extract-papers --spec path/to/spec.json
python3 -m scripts.analyze_past_papers extract-lectures --spec path/to/spec.json
python3 -m scripts.analyze_past_papers extract-answer-keys --spec path/to/spec.json
# Sonnet subagent writes mapping.json here.
python3 -m scripts.analyze_past_papers analyze --spec path/to/spec.json
```
