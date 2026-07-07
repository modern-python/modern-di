---
summary: All docs/README samples constructing a root Container pass explicit validate=, so 2.24.0's UnvalidatedContainerWarning never fires from copy-pasted project samples.
---

# Design: Explicit validate= in all docs samples

## Summary

Every bare root `Container(...)` construction in `docs/` (46 sites at last
count) and the core `README.md` gains an explicit `validate=` argument.
Follow-up to the v3-bridges bundle (2026-07-05.04) ruled in the final review
there: the day 2.24.0 releases, copy-pasted samples would otherwise emit
`UnvalidatedContainerWarning`. The org-wide sibling-repo pass (READMEs +
tests) already merged; this closes the core repo.

## Non-goals

- No prose rewrites; only the constructor calls change (plus a one-line
  mention where a page already discusses validation, if it reads naturally).
- No changes under `modern_di/` or `tests/`.

## Design

Site rules, in order:

1. Default: add `validate=True`.
2. A sample whose graph is deliberately broken to demonstrate a **validation**
   error: `validate=True` (the error is the point).
3. A sample whose graph is deliberately broken to demonstrate a **runtime**
   failure (the lesson requires construction to succeed and the failure to
   happen at resolve time): `validate=False`.
4. A sample that demonstrates `UnvalidatedContainerWarning` itself (the
   to-3.x guide's "before" snippets): stays bare — that is the point.

`build_child_container` calls are untouched (children never take `validate`).

## Testing

- Implementer spot-runs at least one edited sample per docs section
  (quickstart, providers, recipes, integrations, troubleshooting, migration)
  as a script to prove the snippets still execute.
- `just docs-build` (strict) and `just lint-ci` pass.

## Risk

Low. Worst case is an edited sample whose graph does not actually validate —
caught by the spot-runs; any such site falls to rule 3 with a note.
