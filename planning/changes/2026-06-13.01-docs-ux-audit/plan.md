---
date: 2026-06-13
slug: docs-ux-audit
spec: design.md
---

# Plan: Docs UX & Consistency Audit

Execution is a single multi-agent workflow (`Workflow` tool). This plan records
the agent harness so it can be re-run or resumed.

## Phase 1 — Map

One agent inventories the doc surfaces: exact file list under `docs/`, the
mkdocs `nav` order, `README.md`, `architecture/*.md`, and the public-API
docstring surface in `modern_di/`. Returns the work-list for phase 2.
(Done inline before the workflow; passed in as the page list.)

## Phase 2 — Per-page audit (fan-out)

One agent per page / small cluster. Each reads as a fresh user and applies the
seven-lens rubric (onboarding weighted highest), returning structured findings:

```
{ id, surface, location, severity, lens, issue, reader_harm, suggested_fix }
```

Onboarding pages (`index.md`, `introduction/*`, the first integration a newcomer
hits) get an explicit "first-time reader, no prior context" walkthrough.

## Phase 3 — Cross-cutting (fan-out, needs whole set)

Agents that require visibility across all pages:

- **Onboarding journey** — trace index → introduction → first real container as
  one continuous path; where does a newcomer stall, backtrack, or hit an
  unexplained concept?
- **Terminology consistency** — same concept, same word? (scope/lifetime,
  provider/factory, container/child, resolve/inject…)
- **Information architecture** — does the nav grouping and ordering match how a
  user looks for things? Missing cross-links?
- **Cross-surface drift** — docs vs. architecture vs. docstrings: contradictions,
  duplication, divergent explanations.
- **README as front door** — does it earn a click-through and set correct
  expectations?

## Phase 4 — Adversarial verify

Each High/Medium finding is checked by an independent agent: is the reader harm
real, or a style opinion? Is the suggested fix correct and non-breaking?
Refuted findings dropped; survivors carry a verdict.

## Phase 5 — Synthesize

Dedupe across phases, prioritize, and write
`planning/audits/2026-06-13-docs-ux-audit-report.md` in the house format:
Summary, category×severity table, top-5 by impact, then detailed findings with
location + proposed fix. Returned to the user for fix-selection.
