# Subagent Orchestration

This document holds the exact prompt templates the skill uses when it
hands a stage off to a Claude Code subagent via the `Task` tool. The
templates are conservative: they state the task, cite the file paths the
subagent should operate on, and require a specific output shape.

All templates assume the orchestrator (main Claude) has already read the
course spec and knows its resolved paths.

## Stage table (post-upgrade, 10 stages)

| # | Task | Model | Owner |
|---|------|-------|-------|
| 1 | Spec audit | Main Claude | Inline |
| 2 | Paper extraction (MCQ + short-answer + structured) | **Haiku 4.5** | `extract-papers` CLI + this template |
| 3 | Lecture extraction | **Haiku 4.5** | `extract-lectures` CLI + this template |
| 3b | Textbook extraction | **Haiku 4.5** | `extract-textbook` CLI + this template (skip when no textbook) |
| 4 | Answer-key OCR | **Haiku 4.5** | `extract-answer-keys` CLI + this template |
| 5 | KP boundary optimization | **Sonnet 4.6** | `agents/topic-mapper.md` |
| 5b | Pattern taxonomy derivation | **Sonnet 4.6** | `agents/pattern-architect.md` |
| 6 | Question → KP+pattern mapping | **Sonnet 4.6** | `agents/pattern-classifier.md` |
| 7 | KP + pattern statistics (pure Python) | none | `pattern-coverage` and `analyze` CLIs |
| 8 | Tier and pattern interpretation | **Opus 4.7** | `agents/statistical-interpreter.md` |
| 9 | Report assembly (DOCX, XLSX, MD, JSON) | **Haiku 4.5** | `cmd_analyze` already wires the writers; this stage is mostly verifying |

Stage 7 is split internally into two pure-Python invocations:
`pattern-coverage` (fast) and `analyze` (slower, runs sensitivity sweeps).
The orchestrator must run `pattern-coverage` first when patterns are
present so the DOCX writer can pick up the coverage rows.

## Stage 2: Paper extraction (Haiku 4.5)

```text
You are running stage 2 of the past-paper analysis pipeline. Invoke:

    python3 -m scripts.analyze_past_papers extract-papers --spec <SPEC_PATH>

The relaxed parser auto-detects whether each paper is multiple-choice,
short-answer, or fully structured. Open <OUTPUT_DIR>/extracted-papers.json
and summarize:

- Total questions parsed per year, with detected_style per paper
  ("mcq", "short_answer", or "structured").
- Years where warnings fired. Quote each warning verbatim.
- Any year whose question count is below the spec's expected_questions.
- For short-answer / structured papers, sample 3 questions per paper and
  confirm parts (a)/(b)/(c) and per-part marks were captured. Flag any
  paper where parts came back empty.

Do not edit extracted-papers.json. Do not run any LLM-based OCR yourself.
If the extractor failed for a PDF, flag it for stage 4 OCR in your
summary.

Return under 400 words.
```

## Stage 3: Lecture extraction (Haiku 4.5)

```text
You are running stage 3. Invoke:

    python3 -m scripts.analyze_past_papers extract-lectures --spec <SPEC_PATH>

Inspect <OUTPUT_DIR>/extracted-lectures.json and <OUTPUT_DIR>/coverage.json.
Report:

- Number of lectures detected, number of candidate topics, and the mean
  topics per lecture.
- Any lecture whose candidates list is empty.
- The ten highest-coverage topic ids and their shares.
- The number of bullet contexts that look like worked-example seeds
  (matches on "Example", "e.g.", "Exercise"). These will become pattern
  seeds in stage 5b.

Do not modify the JSON files. Return under 300 words.
```

## Stage 3b: Textbook extraction (Haiku 4.5)

Skip this stage when `textbook_pdf` is absent from the spec.

```text
You are running stage 3b. Invoke:

    python3 -m scripts.analyze_past_papers extract-textbook --spec <SPEC_PATH>

Inspect <OUTPUT_DIR>/extracted-textbook.json. Report:

- Number of chapters and sections detected.
- Number of worked examples vs end-of-chapter exercise sets.
- Any chapter whose worked-example list is empty (likely a parser miss).
- The ten chapters with the highest worked-example density (these are
  pattern-rich and seed many entries in stage 5b).

Do not modify the JSON file. Return under 300 words.
```

## Stage 4: Answer-key OCR (Haiku 4.5)

```text
You are running stage 4. First invoke:

    python3 -m scripts.analyze_past_papers extract-answer-keys --spec <SPEC_PATH>

Then, for each year listed in <OUTPUT_DIR>/extracted-answer-keys.json:

1. Read the dumped images in the listed image_dir.
2. Produce structured answer records: question_number, answer_letter (or
   working summary for short-answer), explanation_text.
3. Write a single file <OUTPUT_DIR>/answer-key-ocr.json with the schema
   {"year": ..., "answers": [...]}. Use the question numbers from
   extracted-answer-keys.json when they exist; add new ones when you
   recover them from images.

Only produce answers you are confident in. Every uncertain record must
include a confidence <= 0.5 and a reason.

Return a short progress note (under 200 words).
```

## Stage 5: KP boundary optimization (Sonnet 4.6)

Delegate to the `topic-mapper` subagent (`agents/topic-mapper.md`). The
subagent's prompt template is the file itself; pass these inputs:

```text
You are running stage 5. Read:

- <OUTPUT_DIR>/extracted-lectures.json
- <OUTPUT_DIR>/extracted-textbook.json (if present; use it to validate KP
  boundaries against the canonical chapter structure)

Produce <OUTPUT_DIR>/kps.json with schema_version 2 (each entry has id,
label, lecture_prefix, description, prerequisite_kps,
textbook_chapter_refs, lecture_refs).

Rules:
- Merge near-duplicate candidates under a single canonical label.
- Split a candidate that covers two distinct examinable ideas.
- Preserve the lecture_id prefix; every new KP id must be unique.
- Keep labels examinable, concise, and self-contained.
- Do not invent KPs that are not supported by extracted material.
- Do not write patterns. Patterns belong to stage 5b.
- Do not map questions. Question mapping belongs to stage 6.

Return a change-log summary (merges, splits, new labels) under 400 words.
```

## Stage 5b: Pattern taxonomy derivation (Sonnet 4.6)

Delegate to the `pattern-architect` subagent (`agents/pattern-architect.md`).
Skip when neither textbook nor lecture seeds are available — but if the
spec carried a textbook PDF, this stage is mandatory.

```text
You are running stage 5b. Read:

- <OUTPUT_DIR>/kps.json
- <OUTPUT_DIR>/extracted-lectures.json
- <OUTPUT_DIR>/extracted-textbook.json (when present)

Emit <OUTPUT_DIR>/patterns.json with schema_version 2 covering every
KP. Hard rules:

- Every pattern entry MUST cite at least one source — textbook section,
  worked-example number, or lecture slide. Patterns invented out of thin
  air are rejected.
- Aim for 4-7 patterns per KP. Hard cap 8.
- Each entry includes pattern_id, label, description, given_objects,
  asked_operation, answer_type, skills_invoked, solution_sketch (ordered
  list), common_complications, source.
- pattern_id format is "{kp_id}.P{NN}" with two-digit zero-padded
  index, starting at "P01" per KP.

Return a per-KP table showing pattern_id and label, plus the count of
patterns whose source is exclusively textbook vs exclusively lecture vs
both. Under 600 words.
```

## Stage 6: Question → KP + pattern mapping (Sonnet 4.6)

Delegate to the `pattern-classifier` subagent (`agents/pattern-classifier.md`).

```text
You are running stage 6. Inputs:

- <OUTPUT_DIR>/extracted-papers.json
- <OUTPUT_DIR>/kps.json
- <OUTPUT_DIR>/patterns.json
- (optional) <OUTPUT_DIR>/answer-key-ocr.json

For every question, assign:

- exactly one primary_kp (from kps.json)
- up to two secondary_kps (only when the question genuinely uses the
  KP's machinery, not merely its concepts)
- exactly one pattern_id (from patterns.json; must belong to primary_kp)
- up to two alt_pattern_ids each with confidence in (0, 1]
- prompt_summary, given_objects, asked_operation, answer_type,
  key_steps_observed (<= 4 items), complications, marks, confidence

Year encoding: Jan = .0, Jun = .4, Oct = .8.
Question numbers are strings.

Confidence < 0.7 flags the question for the operator's review queue.

Write to <OUTPUT_DIR>/mapping.json with schema_version 2. Do not edit
upstream files. Do not invent pattern_ids — surface mismatches in your
return summary so stage 5b can be re-run.

Return a table showing distribution of questions per primary_kp and per
pattern_id, plus the count of below-0.7 confidence flags.
```

## Stage 7: Pure-Python statistics (no LLM)

```bash
python3 -m scripts.analyze_past_papers pattern-coverage --spec <SPEC_PATH>
python3 -m scripts.analyze_past_papers analyze         --spec <SPEC_PATH>
```

The orchestrator runs both directly. `pattern-coverage` produces
`pattern-coverage.json` (frequency, recency, saturation, freshness,
predicted_score, pattern tier). `analyze` produces the KP posterior
payload, the sensitivity sweeps, and the four output files (`.json`,
`.xlsx`, `.md`, `.docx`). Do not delegate either stage to an LLM.

## Stage 8: Tier and pattern interpretation (Opus 4.7)

Delegate to the `statistical-interpreter` subagent
(`agents/statistical-interpreter.md`).

```text
You are running stage 8. Read:

- <OUTPUT_DIR>/<course_id>-analysis.json
- <OUTPUT_DIR>/patterns.json
- <OUTPUT_DIR>/pattern-coverage.json
- <OUTPUT_DIR>/tier-narratives.json (if it already exists; you may
  overwrite it)

For every KP with sensitivity_band = "unstable" AND every KP whose tier
is anchor, core, emerging, or legacy, write a 2-4 sentence narrative
plus the structured fields (predicted_pattern, saturated_patterns,
fresh_patterns, drill_set). Decompose anchor / core narratives into
pattern language using pattern_ids verbatim from patterns.json.

Quote posterior_mean, ci_lower_95, ci_upper_95 verbatim from the JSON.
Do not invent numbers. Use the wording "moment-matched Beta posterior"
for the KP layer and "frequency + saturation + freshness" for the
pattern layer. Never claim a credible interval at the pattern level.

drill_set MUST mix recent past-paper occurrences (cite year × question)
with at least one textbook example per fresh pattern when fresh patterns
exist.

Write <OUTPUT_DIR>/tier-narratives.json (schema_version 2). Return a
count of narratives produced plus any KPs you could not explain
confidently.
```

## Stage 9: Report assembly (Haiku 4.5)

```text
You are running stage 9. The pure-Python writer in stage 7 already
produced the .md, .xlsx, .json, and .docx files. The DOCX is the
revision-plan deliverable; the writer reads tier-narratives.json
best-effort, so re-running `analyze` after stage 8 lets it pick up
narratives.

Verify:

1. The DOCX contains Section A (KP frequency tier tables), Section B
   (Pattern predictions per anchor/core KP with decomposition tables,
   already-tested tables, still-possible tables, solution sketches), and
   Section C (Sensitivity & warnings).
2. Unstable KPs are surfaced before tier tables.
3. The markdown carries the same narratives.
4. The DOCX lang flag matches the spec's lang setting (en/zh/both).

If any section is missing, re-run:

    python3 -m scripts.analyze_past_papers analyze --spec <SPEC_PATH>

Do not edit the DOCX or XLSX directly. Return a one-page operator note
listing any open Review_Queue items.
```
