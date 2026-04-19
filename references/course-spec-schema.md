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
| `papers` | array<Paper> | yes | Past papers. See below |
| `answer_keys` | array<AnswerKey> | no | Optional DOCX answer keys |
| `mapping_path` | string | no | Path to a pre-computed question-to-KP mapping JSON. Required when running the statistical stage |
| `coverage_path` | string | no | Path to a pre-computed KP coverage-share JSON. If omitted, the pipeline derives it from the lecture extraction |
| `output_dir` | string | yes | Directory where Excel, JSON, and Markdown outputs will be written |
| `manual_overrides` | array<Override> | no | Hand-edited overrides for persistent OCR or mapping issues |

At least one of `slides_dir` or `notes_pdf` must be present.

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

## Mapping and coverage files

The Python statistical stage does not itself call an LLM. The
question-to-KP mapping and the curriculum-coverage share are prepared by
the Claude Code orchestration layer (see `SKILL.md`) and written to two
JSON files whose paths the spec points at:

### `mapping_path`

```json
{
  "mapping_version": 1,
  "questions": [
    {
      "year": "2020",
      "question_number": 17,
      "primary_kp": "L03.02",
      "secondary_kps": ["L04.01"],
      "confidence": 0.82,
      "justification": "stem asks about carbohydrate anomers"
    }
  ]
}
```

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

Both files must reference KP identifiers that match the lecture
extraction output. When the orchestrator runs with no mapping path it
writes the extracted questions and KPs to disk, then hands off to the
Sonnet topic-mapper subagent to produce the mapping file.

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

## Minimal example

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

## Invariants

- `reference_year` must be greater than or equal to the largest numeric
  `year` in `papers`.
- `lambda_grid` values must lie in `[0, 2]`.
- `tau_grid` values must lie in `[0, 2]`.
- `output_dir` must be writable; the orchestrator creates it if missing.
- Mapping and coverage JSON files, if supplied, must match the KP
  identifiers produced by the lecture-extraction stage.
