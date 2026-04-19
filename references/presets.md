# Presets

A preset bundles default values for a known course so the user does not
have to rediscover them. Presets set `skip_pages`, expected question
counts, preferred extraction modes, and lecture-section naming hints.

Presets are advisory. A spec may override any preset field.

## Manchester School of Biological Sciences, Year 1

These presets cover the core modules the student encounters across terms
one and two. The shared defaults are:

- `skip_pages`: 2 (cover page plus instructions)
- `output_language`: `en`
- `lambda_grid`: `[0.0, 0.2, 0.4]`
- `tau_grid`: `[0.5, 1.0, 2.0]`
- `reference_year`: set by the student to the exam year being prepared for
- Answer keys are usually DOCX with scanned images; enable OCR.

| Preset ID | Course code | Course name | Typical papers | Expected questions |
|-----------|-------------|-------------|----------------|--------------------|
| `biochemistry-manchester` | BIOL10212 | Biochemistry | 2016 to 2020 | 45 |
| `body-systems-manchester` | BIOL10811 | Body Systems | 2017 to 2024 | 25 |
| `molecular-biology-manchester` | BIOL10221 | Molecular Biology | 2016 to 2019 | 50 |
| `drugs-manchester` | BIOL10832 | Drugs | 2016, 2017, 2019 plus infinite-exams pack | 25 |
| `excitable-cells-manchester` | BIOL10822 | Excitable Cells | 2019 (modified), 2021, 2022 (modified) | 25 |
| `from-molecules-to-cells-manchester` | BIOL10000 | From Molecules to Cells | 2021, 2022, 2024 | 40 |
| `ged-manchester` | BIOL10232 | Genes, Evolution and Development | 2016 to 2020 | 50 |
| `chemistry-for-bioscientists-1-manchester` | CHEM10021 | Chemistry for Bioscientists 1 | 2020, 2023, 2024, 2025 | 50 |
| `chemistry-for-bioscientists-2-manchester` | CHEM10022 | Chemistry for Bioscientists 2 | 2017, 2021, 2024, 2025 | 50 |
| `biodiversity-manchester` | BIOL10401 | Biodiversity | 2018, 2020, 2021 | 40 |

## Coverage extraction rules (all Manchester presets)

When the orchestrator computes curriculum coverage from lecture material
it applies these rules in order. The rules live in
`scripts/extract_lectures.py` and the resulting shares feed the Bayesian
prior capped at `tau <= 2`.

1. A line matching `/^(Lecture|L)\s*\d+/` opens a new lecture.
2. A line matching `/^\d+[\.\)]\s+/` opens a candidate topic inside that
   lecture.
3. Bullet and continuation lines attach to the current candidate.
4. Character count of labels plus bullet context defines the topic's raw
   weight. Shares are normalized so that all topic weights sum to 1.0.
5. A topic with zero raw weight is assigned the floor share (0.02) before
   normalization so the prior stays proper.

If a lecture file has no detectable structure (for example a scanned PDF
with no text layer) the preset falls back to the Haiku OCR subagent and
adds a `Review_Queue` entry flagging the lecture as OCR-dependent.

## Syllabus-change handling per preset

Several Manchester papers carry modified-syllabus reprints (for example
`Excitable Cell 2019 paper modified for 2020 syllabus.pdf`). Presets
indicate the expected modification pattern but they do not auto-detect.
The spec author must tag the paper record with `syllabus_version` and,
if desired, `weight_override`. The orchestrator records both values in
the `Method` sheet for auditability.

## When to skip a preset

A preset exists to accelerate setup, not to enforce policy. Override any
of the following when the spec demands it:

- Skip `preset_id` entirely if the course is new or if the Manchester
  formatting diverges (for example a new resit paper format).
- Override `skip_pages` for papers whose cover pages differ.
- Override `expected_questions` when the module publishes a shorter or
  longer paper in a given year.
- Override `syllabus_version` and `weight_override` per paper when a
  rubric is reprinted against a newer syllabus.

## Adding a new preset

1. Read representative papers and lecture material.
2. Record the default skip pages, expected question count, and any quirks
   (for example grouped-context questions, split papers).
3. Add a row to the Manchester table and note the deviations.
4. If the coverage heuristic needs adjustment, file a change to
   `scripts/extract_lectures.py` rather than hiding heuristics inside the
   preset; presets are data, not code.
