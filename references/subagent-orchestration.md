# Subagent Orchestration

This document holds the exact prompt templates the skill uses when it
hands a stage off to a Claude Code subagent via the `Task` tool. The
templates are conservative: they state the task, cite the file paths the
subagent should operate on, and require a specific output shape.

All templates assume the orchestrator (main Claude) has already read the
course spec and knows its resolved paths.

## Stage 2: Paper extraction (Haiku 4.5)

```text
You are running stage 2 of the past-paper analysis pipeline. Invoke:

    python3 -m scripts.analyze_past_papers extract-papers --spec <SPEC_PATH>

Then open <OUTPUT_DIR>/extracted-papers.json and summarize:

- Total questions parsed per year.
- Years where warnings fired. Quote each warning verbatim.
- Any year whose question count is below the spec's expected_questions.

Do not edit extracted-papers.json. Do not run any LLM-based OCR yourself.
If the extractor failed for a PDF, flag it for stage 4 OCR in your summary.

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

Do not modify the JSON files. Return under 300 words.
```

## Stage 4: Answer-key OCR (Haiku 4.5)

```text
You are running stage 4. First invoke:

    python3 -m scripts.analyze_past_papers extract-answer-keys --spec <SPEC_PATH>

Then, for each year listed in <OUTPUT_DIR>/extracted-answer-keys.json:

1. Read the dumped images in the listed image_dir.
2. Produce structured answer records: question_number, answer_letter,
   explanation_text.
3. Write a single file <OUTPUT_DIR>/answer-key-ocr.json with the schema
   {"year": ..., "answers": [...]}. Use the question numbers from
   extracted-answer-keys.json when they exist; add new ones when you
   recover them from images.

Only produce answers you are confident in. Every uncertain record must
include a confidence <= 0.5 and a reason.

Return a short progress note (under 200 words).
```

## Stage 5: KP boundary optimization (Sonnet 4.6)

```text
You are running stage 5. Read <OUTPUT_DIR>/extracted-lectures.json. The
file contains candidate topics drawn mechanically from the lecture text.

Your job is to produce a clean, non-overlapping list of knowledge points
(KPs) for the course. Apply these rules:

1. Merge near-duplicate candidates under a single optimized label.
2. Split a candidate that covers two distinct examinable ideas.
3. Preserve the lecture_id prefix; every new KP id must be unique.
4. Keep the final label concise and examinable ("Michaelis-Menten kinetics"
   rather than "Enzymes lecture 3").

Write the result to <OUTPUT_DIR>/kps.json with the schema:

{
  "kps": [
    {
      "kp_id": "L03.02",
      "lecture_id": "L03",
      "label": "Michaelis-Menten kinetics",
      "source_topic_ids": ["L03.02", "L03.05"],
      "notes": "Merged candidates about Km and Vmax."
    }
  ]
}

Do not invent topics that are not supported by the lecture text. Do not
reassign lecture_id.

Return a change-log summary (merges, splits, new labels).
```

## Stage 6: Question-to-KP mapping (Sonnet 4.6)

```text
You are running stage 6. Inputs:

- <OUTPUT_DIR>/extracted-papers.json
- <OUTPUT_DIR>/kps.json
- (optional) <OUTPUT_DIR>/answer-key-ocr.json

For every question in extracted-papers.json, assign exactly one primary_kp
from kps.json and optional secondary_kps. Write the result to
<OUTPUT_DIR>/mapping.json with the schema:

{
  "mapping_version": 1,
  "questions": [
    {
      "year": "2020",
      "question_number": 17,
      "primary_kp": "L03.02",
      "secondary_kps": [],
      "confidence": 0.8,
      "justification": "stem asks about carbohydrate anomers"
    }
  ]
}

Rules:

- Every question must receive a primary_kp.
- confidence must be in [0, 1]. Below 0.5 means the mapping is a best
  guess and should be re-reviewed by stage 8.
- If the stem is incomplete (OCR gap) leave secondary_kps empty and set
  confidence <= 0.5 with an explicit justification naming the gap.

Do not edit extracted-papers.json or kps.json. Return a table showing
distribution of questions per KP.
```

## Stage 7: Statistical analysis (pure Python, no LLM)

```bash
python3 -m scripts.analyze_past_papers analyze --spec <SPEC_PATH>
```

The orchestrator runs this directly. Do not delegate this stage.

## Stage 8: Tier interpretation (Opus 4.7)

```text
You are running stage 8. Read <OUTPUT_DIR>/<course_id>-analysis.json.

For every KP with sensitivity_band = "unstable" AND every KP whose tier
is anchor, emerging, or legacy, write a one-paragraph rationale (2 to 4
sentences) explaining:

- Why the tier fits the evidence.
- Which hyperparameter swing in Sensitivity_Sweep would flip it, if any.
- Whether the warnings list changes your confidence.

Use language a first-year biology student can read. Do not invent
numbers; quote posterior_mean, ci_lower_95, ci_upper_95 verbatim from
the JSON.

Emit a JSON file <OUTPUT_DIR>/tier-narratives.json with:

{
  "narratives": [
    {"kp_id": "...", "tier": "...", "paragraph": "..."}
  ]
}

Return a count of narratives produced and flag any KP you could not
explain confidently.
```

## Stage 9: Report assembly (Haiku 4.5)

```text
You are running stage 9. Inputs:

- <OUTPUT_DIR>/<course_id>-analysis.md (produced by the pure-Python
  report writer)
- <OUTPUT_DIR>/tier-narratives.json (from stage 8)

Merge the narratives into the Markdown by:

1. Adding a "Tier Narratives" section after the "Tier Summary" section.
2. For each narrative, render "### <kp_id> (<tier>)" then the paragraph.
3. Preserve all existing sections. Do not reorder Unstable Results, do
   not delete Tier Summary rows.

Overwrite the Markdown file in place. Do not touch the Excel or JSON
outputs. Return a diff summary (lines added, sections touched).
```
