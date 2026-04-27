---
name: past-paper-knowledge-point-analysis
description: >
  Suite entry point for past-paper analysis. Routes invocations to the
  `past-paper-orchestrator` skill at `skills/past-paper-orchestrator/`,
  which runs the full hub-and-spokes pipeline (material ingest → KP +
  pattern mapping → statistical analysis → parallel synthesis →
  multi-format render). This file is preserved for backward-compat with
  skill-discovery in single-skill repos. The canonical instructions live
  in the orchestrator's SKILL.md.
triggers:
  - past paper analysis
  - past-paper analysis
  - past-paper-knowledge-point-analysis
  - past paper report
  - exam paper analysis
  - revision report
  - knowledge point analysis
  - kp analysis
---

# Past-Paper Analysis Suite — Entry Point

> **This file is a thin redirect.** The canonical orchestration contract lives at `skills/past-paper-orchestrator/SKILL.md`. Read that file before invoking any spoke.

## What this skill does

Predicts which topics + question patterns will appear on the next sitting of a structured exam, with auditable Bayesian uncertainty + a per-KP cheat-sheet, drill set, and exam-technique coaching prose. Output formats: `.docx`, `.xlsx`, `.md`, `.json`.

## How to invoke

Top-level invocation goes through the orchestrator:

```
Skill(skill="past-paper-orchestrator", args={"spec": "path/to/spec.json", "mode": "analyst", "lang": "en"})
```

Each specialist spoke is also individually invokable — see the seven `skills/<spoke>/SKILL.md` files. They are listed below.

## Suite map

| Skill | Path | Role |
|-------|------|------|
| `past-paper-orchestrator` | `skills/past-paper-orchestrator/` | Hub. Sequences ingest → mapper → stats, then dispatches synthesis specialists in parallel, then renders. |
| `paper-ingest` | `skills/paper-ingest/` | Material extraction (PDFs / DOCX → JSON). Haiku 4.5. |
| `kp-pattern-mapper` | `skills/kp-pattern-mapper/` | KP boundary optimisation + pattern taxonomy + question classification. Sonnet 4.6. |
| `stat-engine` | `skills/stat-engine/` | Pure-Python Bayesian + saturation + freshness statistics. NO LLM. |
| `cheatsheet-writer` | `skills/cheatsheet-writer/` | Per-KP narrative cards. Opus 4.7. |
| `drill-curator` | `skills/drill-curator/` | Drill picks + fresh-pattern challenges. Opus 4.7. |
| `technique-coach` | `skills/technique-coach/` | Exam strategy prose. Opus 4.7. |
| `report-renderer` | `skills/report-renderer/` | Multi-format export. Pure Python. |

## Required reading

All canonical references live under `skills/past-paper-orchestrator/references/`:

- `methodology.md` — statistical source of truth.
- `tier-definitions.md` — KP tiers + parallel pattern tier (`saturated` / `hot` / `fresh` / `dormant`).
- `course-spec-schema.md` — input JSON shape.
- `presets.md` — known courses (Manchester Y1 biology, Edexcel IAL Maths, Manchester Y2/Y3 placeholders).
- `voice-and-conviction.md` — banned phrases, encouraged phrasings, mode-specific tone.
- `report-format.md` — analyst vs student layout spec.
- `companion-skills.md` — when to invoke optional Anthropic companions.
- `subagent-orchestration.md` — historical prompt templates per stage. Superseded by per-spoke SKILL.md files.

## Statistical contract

Every user-facing summary MUST honour the rules in `skills/past-paper-orchestrator/SKILL.md` (Statistical contract section). Highlights:

- Every KP-level probability ships with a credible interval.
- Use **moment-matched Beta posterior** wording for the KP layer. Never say "conjugate posterior".
- Use **frequency + saturation + freshness** wording for the pattern layer. Never claim a credible interval at the pattern level.
- Preserve `tier_reasons` lists verbatim.

## See also

- `README.md` — suite landing page with skill grid + install instructions.
- `references/external-borrowings.md` — provenance log for any open-source lift.
- `install.sh` — multi-profile installer (core / full).
