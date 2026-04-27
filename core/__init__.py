"""Shared pure-Python utilities for the past-paper-analysis suite.

This package holds the cross-skill primitives that several Skills in the
suite depend on:

- ``statistical_model`` — moment-matched Beta posteriors for the KP layer
  and the trend-detection helpers.
- ``pattern_coverage`` — pattern-layer statistics: weighted hits, saturation
  index, freshness flag, predicted score.
- ``sensitivity`` — leave-one-out and (lambda, tau) sensitivity sweeps over
  the KP-level posteriors.
- ``kp_cheatsheet`` — deterministic per-KP cheat-sheet builder consumed by
  the report-renderer skill.

Nothing here makes LLM calls. Skill packages (under ``skills/``) own the
LLM-bound prompts and the data-flow orchestration; ``core`` only owns
pure-Python logic so it can be unit-tested in isolation and re-used by
multiple Skills without duplication.
"""
