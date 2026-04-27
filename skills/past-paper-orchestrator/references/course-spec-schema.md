# Course Spec Schema

A course spec is a single JSON file. The orchestrator (driven by
`SKILL.md`) and the extraction CLIs read it. All paths inside the spec
must be absolute or resolved relative to the spec file itself.

## Top-level fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `course_id` | string | yes | Short identifier, e.g. `BIOL10212` |
| `course_name` | string | yes | Human-readable course name |
| `preset_id` | string | no | Name under `references/presets.md`. Enables defaults |
| `output_language` | string | no | Defaults to `en`. All skill output is English |
| `reference_year` | integer | yes | Year used as the anchor for recency weights (usually the year the student is preparing for) |
| `lambda_grid` | array<number> | no | Recency decay grid. Defaults to `[0.0, 0.2, 0.4]` |
| `tau_grid` | array<number> | no | Prior strength grid. Defaults to `[0.5, 1.0, 2.0]` |
| `lambda` | number | no | Primary recency decay. Defaults to `0.2` |
| `tau` | number | no | Primary prior strength. Defaults to `1.0` |
| `slides_dir` | string | no | Directory of slide decks (PPTX or PDF) |
| `notes_pdf` | string | no | Path to a consolidated lecture-notes PDF |
| `textbook_pdf` | string | no | Path to a textbook PDF aligned to the syllabus. Strongly recommended when patterns are needed — it seeds the pattern taxonomy via the `pattern-architect` agent |
| `papers` | array<Paper> | yes | Past papers. See below |
| `answer_keys` | array<AnswerKey> | no | Optional DOCX answer keys |
| `mapping_path` | string | no | Path to a pre-computed question-to-KP mapping JSON (schema_version 2 supports patterns). Required when running the statistical stage |
| `coverage_path` | string | no | Path to a pre-computed KP coverage-share JSON. If omitted, the pipeline derives it from the lecture extraction |
| `patterns_path` | string | no | Path to a pre-computed `patterns.json`. If omitted, `derive-patterns` writes it inside `output_dir`. Optional only when the user opts out of the pattern layer |
| `pattern_coverage_path` | string | no | Path to a pre-computed `pattern-coverage.json`. If omitted, `pattern-coverage` writes it inside `output_dir` |
| `tier_narratives_path` | string | no | Path to `tier-narratives.json` from the `statistical-interpreter` Opus agent. Read best-effort by `cmd_analyze` so the DOCX can carry per-KP narratives |
| `alpha` | number | no | Pattern-layer novelty bias. Defaults to `0.3`; valid range `[0, 1]`. CLI `--alpha` overrides |
| `fresh_gap_years` | number | no | A pattern is fresh if it has zero hits OR was last seen more than this many years ago. Defaults to `4.0` |
| `lang` | string | no | Report language. One of `en` (default), `zh`, `both`. CLI `--lang` overrides. Skill internals are always English |
| `output_dir` | string | yes | Directory where Excel, JSON, Markdown, and DOCX outputs will be written |
| `docx_output_path` | string | no | Override the DOCX path. Defaults to `{output_dir}/{course_id}-analysis.docx` |
| `manual_overrides` | array<Override> | no | Hand-edited overrides for persistent OCR or mapping issues |

At least one of `slides_dir` or `notes_pdf` must be present. `textbook_pdf`
is optional but strongly recommended for any course where the
revision-plan deliverable should include "still possible" pattern
coverage.

## Paper record

```json
{
  "year": "2020",
  "pdf": "/absolute/path/Biochemistry 2020.pdf",
  "role": "formal",
  "expected_questions": 45,
  "skip_pages": 2,
  "syllabus_version": null,
  "weight_override": null
}
```

- `year` is a string label. It need not be numeric (for example
  `"2022-modified"`) but the `reference_year` math expects numeric
  conversion where possible; non-numeric labels are excluded from the
  posterior unless `weight_override` is set.
- `role` is `formal` or `auxiliary`. Only `formal` papers feed the
  posterior by default; `auxiliary` papers (mock papers, revision tests,
  modified-syllabus reprints) are parsed for coverage but excluded from
  the posterior unless the spec promotes them.
- `expected_questions` (optional) lets the extractor flag under-counts.
- `skip_pages` defaults to 2 (Manchester cover-page layout).
- `syllabus_version` (optional) tags the paper with a version identifier.
  When mixed versions appear across papers, a warning is raised.
- `weight_override` (optional) multiplies the paper's effective weight.
  Use a value less than 1 to down-weight syllabus-change years. The
  default is `null`, which applies the standard recency weight only.

## Answer-key record

```json
{
  "year": "2020",
  "docx": "/absolute/path/Answer Key with Reasoning Biochemistry 2020.docx",
  "image_ocr_dir": "/absolute/path/tmp/answer-key-images/2020"
}
```

- The orchestrator extracts embedded images to `image_ocr_dir` (created
  automatically). The Haiku OCR subagent consumes that directory and
  writes back a structured answer file to the output directory.

## Mapping, coverage, and pattern files

The Python statistical stages do not themselves call an LLM. The
question-to-KP-pattern mapping, the curriculum-coverage share, the
pattern taxonomy, and the per-KP narratives are prepared by the Claude
Code orchestration layer (see `SKILL.md`) and written to JSON files whose
paths the spec points at.

### `mapping_path` (schema_version 2 — pattern-aware)

```json
{
  "course_id": "wma11",
  "schema_version": 2,
  "questions": [
    {
      "year": 2023.4,
      "question_number": "7",
      "primary_kp": "L13.03",
      "secondary_kps": ["L07.02"],
      "pattern_id": "L13.03.P02",
      "alt_pattern_ids": [
        {"pattern_id": "L13.03.P03", "confidence": 0.4}
      ],
      "prompt_summary": "Curve C: 2x^3 - xy + y^2 = 5. Find tangent at (1, 2).",
      "given_objects": ["implicit relation", "point on curve"],
      "asked_operation": "find tangent equation",
      "answer_type": "linear equation",
      "key_steps_observed": [
        "implicit differentiation applied",
        "perpendicularity NOT used"
      ],
      "complications": [],
      "marks": 7,
      "confidence": 0.91
    }
  ]
}
```

Year encoding: January = `.0`, June = `.4`, October = `.8`.
Question numbers are strings to support `"7a"` or roman numerals.
Schema_version `1` (KP-only mapping, no pattern fields) is still tolerated
by the analyzer but disables the pattern layer for that run.

### `coverage_path`

```json
{
  "coverage_version": 1,
  "coverage_shares": {
    "L01.01": 0.05,
    "L01.02": 0.03
  }
}
```

### `patterns_path`

```json
{
  "course_id": "wma11",
  "schema_version": 2,
  "patterns": [
    {
      "kp_id": "L13.03",
      "pattern_id": "L13.03.P02",
      "label": "Find tangent line at a given point on an implicit curve",
      "description": "Standard tangent-line construction after implicit diff.",
      "given_objects": ["implicit relation F(x,y)=0", "point (x0, y0)"],
      "asked_operation": "find equation of tangent line",
      "answer_type": "linear equation y = mx + c",
      "skills_invoked": ["L13.03 implicit diff", "L07.02 perpendicularity"],
      "solution_sketch": [
        "Differentiate both sides implicitly.",
        "Substitute (x0, y0) to get gradient m.",
        "Apply y - y0 = m(x - x0) and simplify."
      ],
      "common_complications": [
        "vertical-tangent edge case",
        "perpendicular-line follow-up"
      ],
      "source": ["textbook §5.4 example 12", "lecture L13 slide 7"]
    }
  ]
}
```

### `pattern_coverage_path`

```json
{
  "course_id": "wma11",
  "schema_version": 2,
  "hyperparameters": {
    "lambda_used": 0.2,
    "alpha_used": 0.3,
    "fresh_gap_years": 4.0,
    "reference_year": 2026.0
  },
  "rows": [
    {
      "kp_id": "L13.03",
      "pattern_id": "L13.03.P02",
      "raw_hits": 4,
      "weighted_hits": 3.41,
      "last_seen_year": 2024.0,
      "first_seen_year": 2017.0,
      "inter_arrival_years_mean": 2.33,
      "inter_arrival_years_max": 4.0,
      "saturation_index": 0.78,
      "freshness_flag": false,
      "predicted_score": 2.61,
      "complications_seen": ["perpendicular-line follow-up"],
      "complications_unseen": ["vertical-tangent edge case"],
      "tier": "saturated",
      "tier_reasons": ["saturation_index=0.78 >= 0.60", "raw_hits=4 >= 2"]
    }
  ]
}
```

### `tier_narratives_path`

```json
{
  "course_id": "wma11",
  "schema_version": 2,
  "narratives": {
    "L13.03": {
      "headline": "Anchor — tangent/normal will appear; pattern P02 is saturated 2022-2024.",
      "narrative": "...",
      "predicted_pattern": "L13.03.P02",
      "saturated_patterns": ["L13.03.P02"],
      "fresh_patterns": ["L13.03.P05"],
      "drill_set": ["2023 Jan Q7", "Textbook §5.4 example 12", "Textbook §5.4 example 14"]
    }
  }
}
```

All files must reference KP and pattern identifiers that match the
lecture / textbook extraction output. When the orchestrator runs with no
mapping path it writes the extracted questions, KPs, and patterns to
disk, then hands off to the Sonnet `topic-mapper`, `pattern-architect`,
and `pattern-classifier` subagents to produce the mapping, pattern, and
coverage files in turn.

## Manual override

```json
{
  "target": "2020-Q17",
  "primary_kp": "L03.02",
  "secondary_kps": ["L04.01"],
  "reason": "OCR garbled the stem; confirmed mapping by hand"
}
```

Overrides are a last resort. They are recorded in the workbook's `Method`
sheet so the audit trail stays intact.

## Minimal example (KP-only — pattern layer disabled)

```json
{
  "course_id": "BIOL10212",
  "course_name": "Biochemistry",
  "preset_id": "biochemistry-manchester",
  "reference_year": 2025,
  "notes_pdf": "/abs/path/Lecture Notes/Biochemistry.pdf",
  "papers": [
    {"year": "2016", "pdf": "/abs/path/Biochemistry 2016.pdf", "role": "formal"},
    {"year": "2017", "pdf": "/abs/path/Biochemistry 2017.pdf", "role": "formal"},
    {"year": "2018", "pdf": "/abs/path/Biochemistry 2018.pdf", "role": "formal"},
    {"year": "2019", "pdf": "/abs/path/Biochemistry 2019.pdf", "role": "formal"},
    {"year": "2020", "pdf": "/abs/path/Biochemistry 2020.pdf", "role": "formal"}
  ],
  "mapping_path": "/abs/path/output/biochemistry/mapping.json",
  "coverage_path": "/abs/path/output/biochemistry/coverage.json",
  "output_dir": "/abs/path/output/biochemistry"
}
```

## Pattern-aware example (textbook + DOCX deliverable)

```json
{
  "course_id": "wma11",
  "course_name": "Edexcel IAL Pure Mathematics 1",
  "preset_id": "edexcel-ial-wma11",
  "reference_year": 2026,
  "notes_pdf": "/abs/path/Lecture Notes/Pure Mathematics 1.pdf",
  "textbook_pdf": "/abs/path/Textbooks/Pearson Edexcel IAL Pure Math 1.pdf",
  "papers": [
    {"year": "2018-Jan", "pdf": "/abs/path/WMA11 Jan 2018.pdf", "role": "formal"},
    {"year": "2024-Jun", "pdf": "/abs/path/WMA11 Jun 2024.pdf", "role": "formal"}
  ],
  "alpha": 0.3,
  "fresh_gap_years": 4.0,
  "lang": "en",
  "output_dir": "/abs/path/output/wma11"
}
```

## Invariants

- `reference_year` must be greater than or equal to the largest numeric
  `year` in `papers`.
- `lambda_grid` values must lie in `[0, 2]`.
- `tau_grid` values must lie in `[0, 2]`.
- `alpha` must lie in `[0, 1]`. `0` reduces the pattern layer to pure
  weighted frequency.
- `fresh_gap_years` must be greater than `0`.
- `lang` must be one of `en`, `zh`, or `both`.
- `output_dir` must be writable; the orchestrator creates it if missing.
- Mapping, coverage, and pattern JSON files, if supplied, must match the
  KP and pattern identifiers produced by the lecture, textbook, and
  pattern-architect stages respectively.
