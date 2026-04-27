# Architecture — Past-Paper Analysis Suite

## TL;DR

Hub-and-spokes Claude Code skill suite. **One** orchestrator at the centre, **seven** specialist skills around it. Sequential stages communicate via JSON files in a shared `output_dir`; parallel synthesis stages communicate via Skill-tool return values. Pure-Python utilities live in `core/`, never duplicated per skill.

```
                                  ┌──────────────────────┐
                                  │   user / Claude      │
                                  └──────────┬───────────┘
                                             │  Skill(skill="past-paper-orchestrator", ...)
                                             ▼
                              ┌──────────────────────────────┐
                              │   past-paper-orchestrator    │
                              │      (hub, Sonnet 4.6)       │
                              └──────────────┬───────────────┘
                                             │ sequential
              ┌──────────────────────────────┼──────────────────────────────┐
              ▼                              ▼                              ▼
      ┌───────────────┐             ┌───────────────────┐           ┌───────────────┐
      │ paper-ingest  │ → JSON →    │ kp-pattern-mapper │ → JSON →  │  stat-engine  │
      │  (Haiku 4.5)  │             │   (Sonnet 4.6)    │           │ (pure Python) │
      └───────────────┘             └───────────────────┘           └───────┬───────┘
                                                                            │ JSON
                                             ┌──────────────────────────────┼──────────────────────────────┐
                                             ▼                              ▼                              ▼
                                  ┌──────────────────┐       ┌──────────────────────┐         ┌──────────────────┐
                                  │ cheatsheet-writer│       │   drill-curator      │         │ technique-coach  │
                                  │    (Opus 4.7)    │  ║    │    (Opus 4.7)        │   ║     │   (Opus 4.7)     │
                                  └────────┬─────────┘  ║    └──────────┬───────────┘   ║     └────────┬─────────┘
                                           │            ║               │               ║              │
                                           │            ║   PARALLEL   ║                ║              │
                                           │            ║   DISPATCH   ║                ║              │
                                           │            └──── single message, three Skill calls ──────┘
                                           ▼                              ▼                              ▼
                                       ┌─────────────────────────────────────────────────────┐
                                       │     report-renderer (pure Python)                   │
                                       │       merges payloads → md / docx / xlsx / json     │
                                       └─────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
                                                   ┌────────────────────┐
                                                   │  output_dir/       │
                                                   │   <course>.docx    │
                                                   │   <course>.xlsx    │
                                                   │   <course>.md      │
                                                   │   <course>.json    │
                                                   └────────────────────┘
```

## Why hub-and-spokes (rather than a flat collection)

Three reasons:

1. **Parallel synthesis is the highest-leverage win.** The old monolithic skill ran `cheatsheet-writer` + `drill-curator` + `technique-coach` work sequentially through a single Opus subagent. Splitting them into three parallel Skill calls is a 2.5–3× wall-clock improvement for the slowest stage. That's only possible if a hub coordinates the dispatch.
2. **Standalone invocation is real.** Users genuinely want to call just `paper-ingest` to extract a few PDFs without running the rest, or just `report-renderer` to regenerate the DOCX from existing JSONs. Each spoke being its own Skill bundle makes that ergonomic.
3. **Mirroring `equity-research-suite` reduces cognitive load.** Same author, same shape, same conventions across two suites. Maintainers and users move between them without remapping their mental model.

## Why file-handoff (sequential) + return-value-handoff (parallel)

Sequential stages (1–4: ingest → mapper → stats) write JSON to `spec.output_dir`. The next stage reads those files. This is robust because each stage is replayable independently — re-running `stat-engine` after a hyperparameter change doesn't require re-running the LLM stages above it.

Parallel synthesis stages (5a/5b/5c) and the renderer (6) pass payloads via Skill-tool return values. Files are heavy; the synthesis stages produce structured cards that the renderer immediately consumes. Writing to disk would just add latency without offering replay benefit (you'd never re-render in isolation — the renderer is fast).

## Data contracts

Every spoke documents its input + output schema in its own `SKILL.md`. The shared `core/` types are the load-bearing contracts:

- `core.statistical_model.KPPosterior` — the per-KP record from stat-engine. Frozen dataclass; every spoke downstream consumes it.
- `core.pattern_coverage.PatternCoverage` — the per-(kp, pattern) cell. Frozen dataclass.
- `core.kp_cheatsheet.KPCheatSheet` — the per-KP cheat-sheet card. Frozen dataclass; `cheatsheet-writer` produces it; `report-renderer` consumes it.
- `core.bilingual_glossary.BilingualGlossary` — JSON-backed glossary used by every spoke that emits ZH prose.

Adding a field to any of these dataclasses is a breaking change across the suite. Renames go through a deprecation cycle: keep the old name as a `@property` for one release, emit a deprecation warning, then drop it.

## Concurrency model

Claude orchestrates. There is no Python event loop driving the suite. The parallel-dispatch step is "send a single message containing three `Skill` tool calls". The runtime executes them concurrently and returns three results to the next turn. The orchestrator's SKILL.md tells Claude exactly when this happens and which three calls to make.

This means:

- The "parallel" in parallel-dispatch is a Claude-Code-runtime fact, not a Python fact.
- If you call the spokes via direct Python imports (e.g. inside the smoke test), they're sequential. That's by design — Python-level testing doesn't need parallelism, but production runs benefit from it.

## Failure modes + retry policy

- **Spec validation fails**: orchestrator stops before any LLM call; user sees a clear missing-input message.
- **`paper-ingest` produces 0 questions for a paper**: warning recorded; downstream stages still run on the remaining papers.
- **`kp-pattern-mapper` produces a mapping with `confidence < 0.7`**: question lands in the `Review_Queue` worksheet of the eventual XLSX.
- **A synthesis spoke times out or returns malformed output**: the orchestrator retries once, then falls back to the deterministic scaffold from `core/kp_cheatsheet.py` (which produces a plain card without the prose fields). The report still renders; the failed section is annotated.
- **`report-renderer` crashes**: the orchestrator dumps all upstream JSONs to `output_dir/.crash-dump/` so the user can re-run the renderer in isolation.

## Governance: external borrowings

Any code or pattern lift from outside this repo lives in `references/external-borrowings.md` with license + last-verified-date + carrier-file columns. CI should reject PRs that introduce new external lifts without a corresponding row.

## See also

- `README.md` — suite landing page with skill grid + install instructions.
- `skills/past-paper-orchestrator/SKILL.md` — orchestration contract (canonical).
- `skills/past-paper-orchestrator/references/methodology.md` — statistical source of truth.
- `~/.claude/plans/users-octavianzhang-desktop-ngal-m1-md-sorted-teapot.md` — original design plan.
