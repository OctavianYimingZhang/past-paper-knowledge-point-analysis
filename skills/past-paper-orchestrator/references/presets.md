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

The Manchester biology presets do not currently bundle a `textbook_pdf`.
The pattern layer can still run from lecture material alone, but pattern
sources will all be `lecture` rather than mixed `textbook + lecture`.
When a textbook PDF is added to a preset, every pattern derived from it
should cite the chapter or worked-example number under `source`.

## Edexcel International Advanced Level (IAL) Mathematics

These presets cover Pearson Edexcel IAL Maths units. **Each unit pairs
with its own Pearson student book**; do not share a textbook between
units. Unit codes are short — Pure 1 to Pure 4 are `WMA11..WMA14`,
Mechanics 1 to Mechanics 3 are `WME01..WME03`, Statistics 1 to
Statistics 3 are `WST01..WST03`. Past papers cover Jan/Jun/Oct sittings;
the spec tags them via the `year` string (e.g. `"2024-Jun"`).

Shared defaults:

- `skip_pages`: 1 (cover page only — Edexcel does not include extended
  formula booklets in the paper PDFs).
- `output_language`: `en` (CLI `--lang` may set zh or both at runtime).
- `lambda_grid`: `[0.0, 0.2, 0.4]`.
- `tau_grid`: `[0.5, 1.0, 2.0]`.
- `alpha`: `0.3` (default novelty bias for the pattern layer).
- `fresh_gap_years`: `4.0`.
- `reference_year`: set by the student to the upcoming sitting year (e.g.
  `2026` to predict the Jan 2026 sitting).

Year encoding for the mapping layer: `Jan = .0`, `Jun = .4`, `Oct = .8`.

| Preset ID | Unit | Unit name | Textbook (Pearson student book) | Typical papers |
|-----------|------|-----------|---------------------------------|----------------|
| `edexcel-ial-wma11` | WMA11 | Pure Mathematics 1 | *Pearson Edexcel IAL Pure Mathematics 1* student book | 2018 Jan onwards |
| `edexcel-ial-wma12` | WMA12 | Pure Mathematics 2 | *Pearson Edexcel IAL Pure Mathematics 2* student book | 2018 Jan onwards |
| `edexcel-ial-wma13` | WMA13 | Pure Mathematics 3 | *Pearson Edexcel IAL Pure Mathematics 3* student book | 2019 Jun onwards |
| `edexcel-ial-wma14` | WMA14 | Pure Mathematics 4 | *Pearson Edexcel IAL Pure Mathematics 4* student book | 2019 Jun onwards |
| `edexcel-ial-wme01` | WME01 | Mechanics 1 | *Pearson Edexcel IAL Mechanics 1* student book | 2014 Jan onwards |
| `edexcel-ial-wme02` | WME02 | Mechanics 2 | *Pearson Edexcel IAL Mechanics 2* student book | 2014 Jan onwards |
| `edexcel-ial-wme03` | WME03 | Mechanics 3 | *Pearson Edexcel IAL Mechanics 3* student book | 2014 Jan onwards |
| `edexcel-ial-wst01` | WST01 | Statistics 1 | *Pearson Edexcel IAL Statistics 1* student book | 2014 Jan onwards |
| `edexcel-ial-wst02` | WST02 | Statistics 2 | *Pearson Edexcel IAL Statistics 2* student book | 2014 Jan onwards |
| `edexcel-ial-wst03` | WST03 | Statistics 3 | *Pearson Edexcel IAL Statistics 3* student book | 2014 Jan onwards |

### Textbook uniqueness invariant

Each Edexcel preset's `textbook_pdf` path must be unique to its
`course_id`. Pure 1 and Pure 3 cover overlapping topics but use different
student books with different worked-example sets and different
end-of-chapter exercises, so the pattern taxonomy must be derived from
the unit's own book. The CLI's preset-loader asserts uniqueness; sharing
a textbook path between two units fails fast.

### Why short-answer parser is required

Every Edexcel IAL Maths paper is structured (questions with
parts (a)/(b)/(c) and per-part marks). The relaxed parser introduced in
the upgrade auto-detects this style — you should see
`detected_style: "structured"` in `extracted-papers.json` for every paper
of these presets.

## Manchester School of Biological Sciences, Year 2

These presets cover Year 2 modules. Course codes are not yet recorded in
this file: the actual School of Biological Sciences module codes follow
the `BIOL2xxxx` family but the precise four-digit suffixes need to be
looked up in the school handbook before being committed. Until that
lookup is done, the `Course code` column carries the placeholder
`BIOL2????` rather than an invented value.

Shared defaults match the Year 1 block (`skip_pages: 2`,
`output_language: en`, `lambda_grid: [0.0, 0.2, 0.4]`,
`tau_grid: [0.5, 1.0, 2.0]`, OCR enabled for DOCX answer keys with
scanned images).

`Expected questions` is left blank below. Year 2 papers vary between
short-answer, structured, and essay-only formats and the per-paper count
should be set in the spec rather than guessed at the preset level.

| Preset ID | Course code | Course name | Typical papers | Expected questions |
|-----------|-------------|-------------|----------------|--------------------|
| `animal-behaviour-manchester-y2` | BIOL2???? | Animal Behaviour | 2021 to 2025 (selected) |  |
| `animal-diversity-manchester-y2` | BIOL2???? | Animal Diversity | 2018 to 2023 (selected) |  |
| `animal-physiology-manchester-y2` | BIOL2???? | Animal Physiology | 2023 to 2025 |  |
| `anatomy-special-sense-organs-manchester-y2` | BIOL2???? | Anatomy of the Special Sense Organs | 2023 to 2024 |  |
| `body-systems-2-manchester-y2` | BIOL2???? | Body Systems 2 | 2021 to 2024 (selected) |  |
| `cell-adhesion-manchester-y2` | BIOL2???? | Cell Adhesion | 2023 to 2025 |  |
| `cell-membrane-structure-function-manchester-y2` | BIOL2???? | Cell Membrane Structure & Function | 2016 to 2025 (selected) |  |
| `cell-metabolism-metabolic-control-manchester-y2` | BIOL2???? | Cell Metabolism & Metabolic Control | 2022 to 2024 |  |
| `chemistry-of-biomolecules-manchester-y2` | BIOL2???? | Chemistry of Biomolecules | 2016 to 2025 (selected) |  |
| `clinical-drug-development-manchester-y2` | BIOL2???? | Clinical Drug Development | 2015 to 2024 (selected) |  |
| `drugs-and-the-brain-manchester-y2` | BIOL2???? | Drugs and the Brain | 2018 to 2025 (selected) |  |
| `fundamentals-of-bacteriology-manchester-y2` | BIOL2???? | Fundamentals of Bacteriology | 2023 to 2025 |  |
| `fundamentals-of-evolutionary-biology-manchester-y2` | BIOL2???? | Fundamentals of Evolutionary Biology | 2016 to 2025 (selected) |  |
| `gut-and-renal-human-physiology-manchester-y2` | BIOL2???? | Gut and Renal Human Physiology | 2016 |  |
| `haematology-manchester-y2` | BIOL2???? | Haematology | 2016 to 2025 (selected) |  |
| `how-to-make-a-brain-manchester-y2` | BIOL2???? | How to Make a Brain | 2017 to 2025 (selected) |  |
| `human-anatomy-histology-manchester-y2` | BIOL2???? | Human Anatomy & Histology | 2016 to 2025 (selected, plus mock) |  |
| `immunology-manchester-y2` | BIOL2???? | Immunology | 2016 to 2025 (selected) |  |
| `introduction-to-cancer-manchester-y2` | BIOL2???? | Introduction to Cancer | 2023 to 2025 |  |
| `introduction-to-virology-manchester-y2` | BIOL2???? | Introduction to Virology | 2023 to 2025 |  |
| `membrane-excitability-manchester-y2` | BIOL2???? | Membrane Excitability | 2016 to 2025 (selected, plus 2022 mock) |  |
| `molecules-cells-human-disease-manchester-y2` | BIOL2???? | Molecules and Cells in Human Disease | 2018 to 2025 (selected) |  |
| `motor-systems-manchester-y2` | BIOL2???? | Motor Systems | 2016 to 2025 (selected) |  |
| `motor-systems-hci-manchester-y2` | BIOL2???? | Motor Systems for Human Computer Interaction | 2024 |  |
| `omic-technologies-resources-manchester-y2` | BIOL2???? | Omic Technologies and Resources | 2017 to 2025 (selected, plus example paper) |  |
| `organismal-genetics-manchester-y2` | BIOL2???? | Organismal Genetics | 2023 to 2025 |  |
| `parasitology-manchester-y2` | BIOL2???? | Parasitology | 2017 to 2025 (selected) |  |
| `plants-for-the-future-manchester-y2` | BIOL2???? | Plants for the Future | 2016 to 2025 (selected) |  |
| `principles-of-developmental-biology-manchester-y2` | BIOL2???? | Principles of Developmental Biology | 2015 to 2025 (selected) |  |
| `principles-of-infectious-disease-manchester-y2` | BIOL2???? | Principles of Infectious Disease | 2023 to 2025 |  |
| `proteins-manchester-y2` | BIOL2???? | Proteins | 2015 to 2025 (selected) |  |
| `sensory-systems-manchester-y2` | BIOL2???? | Sensory Systems | 2017 to 2025 (selected) |  |
| `sensory-systems-hci-manchester-y2` | BIOL2???? | Sensory Systems for HCI | 2024 |  |
| `the-dynamic-cell-manchester-y2` | BIOL2???? | The Dynamic Cell | 2015 to 2024 (selected) |  |

### Style

Year 2 modules in this list are predominantly structured short-answer
papers with mixed parts per question. None of the Year 2 module names
above carry the `Essay Paper` or `Problem Paper` qualifier that Year 3
exam papers use, so essay-only or pure problem-paper formats are not the
expected default. Where a paper has an explicit `Mock` PDF (for example
Membrane Excitability 2022 Mock, Drugs and the Brain 2023 Mock, Human
Anatomy & Histology Mock) the mock is recorded as a paper of the same
style as the live exam in that year.

## Manchester School of Biological Sciences, Year 3

These presets cover Year 3 modules. As with Year 2 above, course codes
are placeholders (`BIOL3????`) until the actual School of Biological
Sciences four-digit module suffixes are looked up. Year 3 corpora
include both live exam papers and `Essay Paper` and `Problem Paper`
variants for several themes (Biochemistry, Biology, Biomedical Sciences,
Cell Biology, Developmental Biology, Genetics, Immunology, Medical
Biochemistry, Medical Physiology, Microbiology, Molecular Biology,
Neuroscience, Pharmacology, Pharmacology & Physiology, Plant Sciences,
Zoology, Anatomical Sciences, Biology with Science & Society,
Biotechnology). Each themed Essay or Problem paper is treated as its
own preset because the rubric and expected response shape differ from
the live module exams.

Shared defaults match the Year 1 block. `Expected questions` is again
left blank — essay papers usually require 2 to 4 long-form answers,
problem papers usually require 4 to 8 structured answers, and
module-specific live papers vary; the per-paper count should be set in
the spec.

| Preset ID | Course code | Course name | Typical papers | Expected questions |
|-----------|-------------|-------------|----------------|--------------------|
| `advanced-behavioural-evolutionary-ecology-manchester-y3` | BIOL3???? | Advanced Behavioural & Evolutionary Ecology | 2023, 2025 |  |
| `advanced-developmental-biology-manchester-y3` | BIOL3???? | Advanced Developmental Biology | 2018 to 2024 (selected) |  |
| `advanced-endocrinology-manchester-y3` | BIOL3???? | Advanced Endocrinology | 2024 to 2025 |  |
| `advanced-immunology-manchester-y3` | BIOL3???? | Advanced Immunology | 2016 to 2025 (selected) |  |
| `advanced-parasitology-manchester-y3` | BIOL3???? | Advanced Parasitology | 2023 to 2025 |  |
| `advances-in-anatomical-sciences-manchester-y3` | BIOL3???? | Advances in Anatomical Sciences | 2017, 2023 |  |
| `anatomical-sciences-essay-paper-manchester-y3` | BIOL3???? | Anatomical Sciences Essay Paper | 2023 to 2024 |  |
| `bacterial-infections-of-man-manchester-y3` | BIOL3???? | Bacterial Infections of Man | 2023 |  |
| `biochemistry-essay-paper-manchester-y3` | BIOL3???? | Biochemistry Essay Paper | 2017 to 2025 (selected) |  |
| `biochemistry-problem-paper-manchester-y3` | BIOL3???? | Biochemistry Problem Paper | 2016 |  |
| `biochemical-basis-of-disease-manchester-y3` | BIOL3???? | Biochemical Basis of Disease | 2023 to 2025 |  |
| `biology-essay-paper-manchester-y3` | BIOL3???? | Biology Essay Paper | 2024 to 2025 |  |
| `biology-problem-paper-manchester-y3` | BIOL3???? | Biology Problem Paper | 2022 |  |
| `biology-science-society-essay-paper-manchester-y3` | BIOL3???? | Biology with Science & Society Essay Paper | 2023 to 2025 |  |
| `biomedical-sciences-essay-paper-manchester-y3` | BIOL3???? | Biomedical Sciences Essay Paper | 2023 to 2025 |  |
| `biomedical-sciences-problem-paper-manchester-y3` | BIOL3???? | Biomedical Sciences Problem Paper | 2019 |  |
| `biotechnology-essay-paper-manchester-y3` | BIOL3???? | Biotechnology Essay Paper | 2023 to 2025 |  |
| `biotic-interactions-manchester-y3` | BIOL3???? | Biotic Interactions | 2019, 2024 |  |
| `cardiovascular-systems-manchester-y3` | BIOL3???? | Cardiovascular Systems | 2023 to 2025 |  |
| `cell-adhesion-manchester-y3` | BIOL3???? | Cell Adhesion | 2012 to 2025 (selected) |  |
| `cell-biology-essay-paper-manchester-y3` | BIOL3???? | Cell Biology Essay Paper | 2023 to 2024 |  |
| `cell-signalling-manchester-y3` | BIOL3???? | Cell Signalling | 2016 to 2025 (selected) |  |
| `chemical-communication-in-animals-manchester-y3` | BIOL3???? | Chemical Communication in Animals | 2023 |  |
| `chemistry-of-biological-processes-manchester-y3` | BIOL3???? | Chemistry of Biological Processes | 2017 to 2025 (selected) |  |
| `clocks-sleep-rhythms-of-life-manchester-y3` | BIOL3???? | Clocks, Sleep & the Rhythms of Life | 2015 to 2025 (selected) |  |
| `comparative-developmental-biology-manchester-y3` | BIOL3???? | Comparative Developmental Biology | 2023 to 2024 |  |
| `conservation-biology-manchester-y3` | BIOL3???? | Conservation Biology | 2023 to 2025 |  |
| `developmental-biology-essay-paper-manchester-y3` | BIOL3???? | Developmental Biology Essay Paper | 2023 to 2024 |  |
| `evolution-genes-genomes-systems-manchester-y3` | BIOL3???? | Evolution of Genes, Genomes & Systems | 2018 to 2025 (selected) |  |
| `gene-regulation-disease-manchester-y3` | BIOL3???? | Gene Regulation & Disease | 2016 to 2025 (selected, includes 2024 CADMUS) |  |
| `genetics-essay-paper-manchester-y3` | BIOL3???? | Genetics Essay Paper | 2016 to 2025 (selected) |  |
| `glycobiology-manchester-y3` | BIOL3???? | Glycobiology (Glycan Functions / Glycobiology in Health & Disease) | 2017 to 2025 (selected) |  |
| `green-biotechnology-manchester-y3` | BIOL3???? | Green Biotechnology | 2023 to 2025 |  |
| `hormones-and-behaviour-manchester-y3` | BIOL3???? | Hormones & Behaviour | 2016 to 2025 (selected, plus question bank) |  |
| `human-anatomy-histology-mock-manchester-y3` | BIOL3???? | Human Anatomy & Histology (Year 3 mock) | Mock |  |
| `human-genetics-evolution-manchester-y3` | BIOL3???? | Human Genetics & Evolution | 2023 to 2025 |  |
| `human-impacts-on-the-biosphere-manchester-y3` | BIOL3???? | Human Impacts on the Biosphere | 2016 to 2023 (selected) |  |
| `human-reproductive-biology-manchester-y3` | BIOL3???? | Human Reproductive Biology | 2016 to 2025 (selected) |  |
| `imaging-in-biomedical-research-manchester-y3` | BIOL3???? | Imaging in Biomedical Research | 2023 |  |
| `immune-response-disease-manchester-y3` | BIOL3???? | Immune Response & Disease | 2023, 2025 |  |
| `immunology-essay-paper-manchester-y3` | BIOL3???? | Immunology Essay Paper | 2023 to 2025 |  |
| `introduction-to-nanomedicine-manchester-y3` | BIOL3???? | Introduction to Nanomedicine | 2025 |  |
| `learning-memory-cognition-manchester-y3` | BIOL3???? | Learning, Memory & Cognition | 2017 to 2025 (selected) |  |
| `macromolecular-recognition-manchester-y3` | BIOL3???? | Macromolecular Recognition in Biological Systems | 2017 to 2025 (selected) |  |
| `medical-biochemistry-essay-paper-manchester-y3` | BIOL3???? | Medical Biochemistry Essay Paper | 2023 to 2025 |  |
| `medical-physiology-essay-paper-manchester-y3` | BIOL3???? | Medical Physiology Essay Paper | 2023 to 2025 |  |
| `membrane-transport-signalling-health-disease-manchester-y3` | BIOL3???? | Membrane Transport & Signalling in Health & Disease | 2023 to 2025 |  |
| `microbiology-essay-paper-manchester-y3` | BIOL3???? | Microbiology Essay Paper | 2023 to 2025 |  |
| `molecular-biology-essay-paper-manchester-y3` | BIOL3???? | Molecular Biology Essay Paper | 2021 to 2025 (selected) |  |
| `molecular-biology-of-cancer-manchester-y3` | BIOL3???? | Molecular Biology of Cancer | 2023 to 2025 |  |
| `neuroinflammation-health-disease-manchester-y3` | BIOL3???? | Neuroinflammation in Health & Disease | 2023 to 2025 (includes 2024 CADMUS) |  |
| `neuropharmacology-human-health-manchester-y3` | BIOL3???? | Neuropharmacology of Human Health | 2017 to 2025 (selected) |  |
| `neuroscience-essay-paper-manchester-y3` | BIOL3???? | Neuroscience Essay Paper | 2013 to 2025 (selected) |  |
| `neuroscience-problem-paper-manchester-y3` | BIOL3???? | Neuroscience Problem Paper | 2001 to 2024 (selected, mixed PP1/PP2) |  |
| `pharmacology-essay-paper-manchester-y3` | BIOL3???? | Pharmacology Essay Paper | 2023 to 2025 |  |
| `pharmacology-physiology-essay-paper-manchester-y3` | BIOL3???? | Pharmacology & Physiology Essay Paper | 2023 to 2024 |  |
| `plant-sciences-essay-paper-manchester-y3` | BIOL3???? | Plant Sciences Essay Paper | 2023 to 2024 |  |
| `post-genome-biology-manchester-y3` | BIOL3???? | Post-Genome Biology | 2016 to 2026 (selected, includes 2026 mock) |  |
| `protein-assembly-dynamics-function-manchester-y3` | BIOL3???? | Protein Assembly, Dynamics & Function | 2016 to 2025 (selected) |  |
| `protein-sorting-manchester-y3` | BIOL3???? | Protein Sorting | 2016 to 2025 (selected) |  |
| `role-of-diagnostics-in-medicine-manchester-y3` | BIOL3???? | Role of Diagnostics in Medicine | 2022 to 2025 |  |
| `stem-cells-manchester-y3` | BIOL3???? | Stem Cells | 2016 to 2025 (selected) |  |
| `toxins-toxicants-toxicity-manchester-y3` | BIOL3???? | Toxins, Toxicants & Toxicity | 2017 to 2025 (selected) |  |
| `zoology-essay-paper-manchester-y3` | BIOL3???? | Zoology Essay Paper | 2024 to 2025 |  |

### Style

Year 3 modules split into three groups by paper format, inferred from
the module name:

- **Essay-only** — every module whose name ends in `Essay Paper`
  (Anatomical Sciences, Biochemistry, Biology, Biology with Science &
  Society, Biomedical Sciences, Biotechnology, Cell Biology,
  Developmental Biology, Genetics, Immunology, Medical Biochemistry,
  Medical Physiology, Microbiology, Molecular Biology, Neuroscience,
  Pharmacology, Pharmacology & Physiology, Plant Sciences, Zoology).
  Expect 2 to 4 long-form essay prompts per paper with no
  short-answer scaffolding.
- **Structured problem paper** — modules whose name ends in
  `Problem Paper` (Biochemistry, Biology, Biomedical Sciences,
  Neuroscience). Expect 4 to 8 multi-part structured questions per
  paper, with explicit per-part marks rather than a single
  free-response prompt.
- **Module exam (mixed)** — every other Year 3 module. Default to
  structured short-answer with mixed parts per question, the same
  shape as the Year 2 live exams, until a per-paper override says
  otherwise.

Where the format guess is uncertain (for example
`Advances in Anatomical Sciences` and `Bacterial Infections of Man`
have very few archived years and could be either structured or essay
in any given sitting), the spec author should set
`detected_style` per paper at extraction time rather than relying on
the preset default.

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
