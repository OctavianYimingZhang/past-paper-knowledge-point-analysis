# Past-Paper Analysis Suite

A multi-skill Claude Code suite for predicting **what** topics will appear on the next sitting of a structured exam AND **how** they will be tested. Hub-and-spokes shape: one orchestrator dispatches material ingest → KP/pattern mapping → statistical analysis sequentially, then fans out cheat-sheet, drill-curation, and exam-technique writing **in parallel** before assembling a multi-format report.

Built on the same architectural pattern as [`equity-research-suite`](https://github.com/OctavianYimingZhang/equity-research-suite) (same author).

## What it produces

For every knowledge point (KP) in your course, the suite emits:

- A **moment-matched Beta posterior** with a 95% credible interval over "this topic appears next sitting".
- A **tier assignment** — `anchor`, `core`, `emerging`, `legacy`, `oneoff`, `not_tested` — driven by deterministic rules with auditable `tier_reasons`.
- A **pattern decomposition**: which question variants the examiner has been recycling (`saturated`), which they've started using recently (`hot`), which the syllabus seeds but they haven't picked up in 4+ years (`fresh`), and which appear once and then drop (`dormant`).
- A **cheat-sheet card**: tier rationale, dominant pattern, "already tested" rows citing real `(year, question_number)` tuples, "still possible" rows for fresh patterns, narrative + how-it-will-be-tested prose.
- A **drill set** of 5–8 past-paper questions per anchor / core KP plus 1–2 fresh-pattern construction prompts.
- **Exam-technique coaching** prose: approach, marks-walk, common traps, examiner signal, pre-read checklist.

Output formats: `.docx` (the headline revision-plan deliverable), `.xlsx` (drill-down audit), `.md` (git-friendly diff), `.json` (re-runs).

## Suite layout

```
past-paper-analysis-suite/
├── skills/                          # One Skill bundle per stage / specialist
│   ├── past-paper-orchestrator/     # [Hub] Dispatches the rest
│   │   ├── SKILL.md
│   │   └── references/              # methodology, tier definitions, voice rules, format spec
│   ├── paper-ingest/                # [Spoke] Haiku 4.5 — extract papers / lectures / textbook / answer keys
│   ├── kp-pattern-mapper/           # [Spoke] Sonnet 4.6 — KP → pattern → mapping
│   ├── stat-engine/                 # [Spoke] Pure Python — Beta posteriors + saturation + freshness
│   ├── cheatsheet-writer/           # [Spoke] Opus 4.7 — per-KP narrative cards
│   ├── drill-curator/               # [Spoke] Opus 4.7 — drill picks + fresh challenges
│   ├── technique-coach/             # [Spoke] Opus 4.7 — exam strategy prose
│   └── report-renderer/             # [Spoke] Pure Python — multi-format export
├── core/                            # Shared pure-Python utilities
│   ├── statistical_model.py
│   ├── pattern_coverage.py
│   ├── sensitivity.py
│   ├── kp_cheatsheet.py
│   └── bilingual_glossary.py
├── scripts/                         # CLI orchestrator + extraction modules + writers
│   ├── analyze_past_papers.py
│   ├── extract_papers.py            # MCQ + short-answer + structured-paper parser
│   ├── extract_lectures.py
│   ├── extract_textbook.py
│   ├── extract_answer_keys.py
│   └── report_writer/
├── references/
│   └── external-borrowings.md       # Provenance log gating any open-source lift
├── tests/                           # 166 tests; pytest -q
└── install.sh                       # Suite installer (core / full profiles)
```

## Skill grid

| Skill | Role | Mode A (standalone) | Mode B (embedded) | Model |
|-------|------|---------------------|-------------------|-------|
| `past-paper-orchestrator` | Hub: pipeline + parallel synthesis dispatch | n/a (entry point) | n/a | (orchestrates) |
| `paper-ingest` | Material extraction | Returns extracted JSONs + warning summary | Returns paths only | Haiku 4.5 |
| `kp-pattern-mapper` | KP + pattern + question mapping | Returns full taxonomy + diagnostics | Returns paths + 1-line summary | Sonnet 4.6 |
| `stat-engine` | Bayesian + saturation statistics | Returns posteriors + tier table | Same | Pure Python (no LLM) |
| `cheatsheet-writer` | Per-KP narrative cards | Markdown rendering | Structured cards | Opus 4.7 |
| `drill-curator` | Drill picks + fresh challenges | Markdown bullet list | JSON cards | Opus 4.7 |
| `technique-coach` | Exam strategy prose | Markdown coaching doc | JSON inserts | Opus 4.7 |
| `report-renderer` | Multi-format export | Files in `output/` | Same | Pure Python (no LLM) |

Synthesis spokes 4–6 (`cheatsheet-writer`, `drill-curator`, `technique-coach`) **must** be dispatched in a single message (three concurrent `Skill` tool calls). Sequential dispatch is the bottleneck the suite eliminates.

## Installation

Python 3.11 or newer is required.

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Symlink each skill into ~/.claude/skills/
./install.sh                    # core profile (1 hub + 7 spokes)
./install.sh full               # core + verifies Anthropic companions are reachable
./install.sh --dry-run          # preview without changes
./install.sh --uninstall        # remove all suite symlinks
```

The installer is non-destructive: it symlinks instead of copying, refuses to overwrite paths it didn't create, and writes `~/.claude/skills/.past-paper-suite-manifest` so a later `--uninstall` is clean.

## Usage

Top-level invocation goes through the orchestrator skill:

```
past-paper-orchestrator --spec /path/to/course-spec.json --mode analyst --lang en
```

Modes:
- `analyst` (default): dense revision deliverable. Compact executive summary, per-KP cheat-sheet middle, methodology appendix.
- `student`: friendlier. Drops the methodology appendix, drops Bayesian jargon from the body, front-loads the recommended drill set.

Languages:
- `en` (default), `zh`, `both` (stacked CN-then-EN, never side-by-side).

Each spoke is also individually invokable. Example: regenerate just the cheat-sheets from existing analysis JSONs:

```
cheatsheet-writer --analysis output/<course>-analysis.json \
                  --pattern-coverage output/pattern-coverage.json \
                  --mapping output/mapping.json \
                  --mode student --lang both
```

See each spoke's `SKILL.md` for its standalone contract.

## Tests

```bash
pytest -q
```

Currently 166 tests across:
- `tests/test_statistical_model.py` — KP posterior, tier assignment, trend detection.
- `tests/test_pattern_coverage.py` — saturation, freshness, predicted score.
- `tests/test_sensitivity.py` — sensitivity sweep, leave-one-out stability.
- `tests/test_kp_cheatsheet.py` — cheat-sheet assembly.
- `tests/test_extract_papers.py`, `test_extract_textbook.py` — parsers.
- `tests/test_report_writer_docx.py` — DOCX rendering.
- `tests/test_bilingual_glossary.py` — glossary persistence.
- `skills/past-paper-orchestrator/tests/test_orchestration_smoke.py` — end-to-end smoke + suite-shape invariants.

## Statistical contract

- Every KP-level probability ships with a credible interval. A point estimate without its interval is a bug.
- The KP layer is a **moment-matched Beta** approximation under recency-weighted hits. The word "conjugate" is banned in user-facing output (it is an approximation, not a strict conjugate update).
- The pattern layer is **frequency + saturation + freshness**. With ≤ 5 hits per cell, a Beta posterior is uselessly wide. The suite is honest about that — pattern-level claims never carry credible intervals.
- `lambda` is swept over `{0, 0.2, 0.4}` and `tau` over `{0.5, 1.0, 2.0}` by default. KPs that flip tiers across the sweep are tagged `unstable` and surfaced first.
- Every claim in the prose layer is defensible from the data — cite a `(year, question_number)`, a saturation index, a posterior, a tier reason, or a textbook section.

Full details in `skills/past-paper-orchestrator/references/methodology.md`.

## External borrowings

Every code or pattern lift from outside this repo is logged in `references/external-borrowings.md` with license + last-verification date + carrier file. Lifts without a row there are unauthorised; reviewers should reject them.

## License

MIT. See `LICENSE`.
