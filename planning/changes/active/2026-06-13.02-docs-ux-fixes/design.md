---
status: active
date: 2026-06-13
slug: docs-ux-fixes
supersedes: null
superseded_by: null
pr: 212
outcome: null
---

# Design: Docs UX fixes (all 16 Medium audit findings)

## Summary

Fix every Medium-severity finding from the 2026-06-13 Docs UX & Consistency
audit ([report](../../../audits/2026-06-13-docs-ux-audit-report.md)). These are
documentation edits — runnable-example fixes, accuracy corrections, missing
cross-links/sections, and one small nav restructure. No library code changes.

## Motivation

The audit found 0 High, 16 Medium, 54 Low. The Mediums cluster on the new-user
onboarding path (README has no install/example; the Quickstart's first example
silently no-ops; several examples don't run) plus cross-surface accuracy drift
(a mislabelled exception, an undocumented exception, inconsistent missing-context
docs). Each is cheap to fix and individually verifiable.

## Scope

The 16 distinct Mediums (19 report IDs; O-1≡R-1 and D-21≡X-4 are the same defect
flagged twice): O-1/R-1, O-2, O-3, O-4, O-5, O-6, O-7, D-1, D-11, D-19, D-21/X-4,
D-23, D-25, A-3, X-1, X-2, X-3. The 54 Lows are out of scope for this bundle.

## Non-goals

- The 54 Low findings (separate follow-up if desired).
- Any change to `modern_di/` library code — docs only.
- Re-running the audit.

## Verification

- **Runnable examples** are extracted and executed with the project interpreter
  (`uv run python`) and must exit 0 (and, where stated, produce output).
- **Rendering / cross-links** are checked with `mkdocs build --strict` (fails on
  broken internal links) plus HTML inspection for the ordered-list fix.
- Two findings (O-5 Litestar websocket, O-6 FastAPI `setup_di`/lifespan) depend
  on behavior in the sibling integration repos (`../modern-di-litestar`,
  `../modern-di-fastapi`). Both mechanics were **confirmed from source** and the
  tasks now carry the exact fix: O-5 — `di_container` auto-resolves by name
  (plugin registers it), so only the undefined `MyService`/`ALL_GROUPS` need
  fixing; O-6 — `setup_di` merges with any custom lifespan and closes the
  container itself (so don't also `async with container`).

## Risk

- O-5/O-6 mechanics could be stated wrong if the sibling-repo behavior isn't
  verified — mitigated by gating those tasks on confirmation.
- The X-3 nav split touches `mkdocs.yml`; mitigated by `mkdocs build --strict`.

## Deliverable & follow-up

All 16 Mediums fixed on this branch; `mkdocs build --strict` green. On ship,
hand-edit any affected `architecture/*.md`, move both this bundle and the
`2026-06-13.01-docs-ux-audit` bundle to `archive/` with `status: shipped` + `pr:`.
