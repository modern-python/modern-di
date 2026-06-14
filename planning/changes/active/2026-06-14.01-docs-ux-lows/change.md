---
status: active
date: 2026-06-14
slug: docs-ux-lows
supersedes: null
superseded_by: null
pr: null
outcome: null
---

# Change: Docs UX audit — fix the 53 Low findings

**Lane:** batch follow-up to the 2026-06-13 docs UX audit. Not a design change —
mechanical doc edits (cross-links, imports, terminology, glosses, four
docstrings) driven directly by the verified findings in
[`audits/2026-06-13-docs-ux-audit-report.md`](../../../audits/2026-06-13-docs-ux-audit-report.md).
The 16 Mediums shipped in #212; this clears the Lows.

## Goal

Apply every Low-severity finding (O-8…O-17, D-2…D-26 lows, R-2, A-1/A-2/A-4/A-5/A-6,
DS-1…DS-4, X-5…X-17). `D-10` is already resolved by the X-3 split shipped in #212.

## Approach

Grouped by file (the audit gives an exact location + suggested fix for each).
Most are one-liners: missing/unused imports, inline cross-links, terminology
normalization, short glosses, two small example rewrites. DS-1…DS-4 add four
well-formed docstrings to `modern_di/` (D1 is ignored but D211/D212/D415 are
active — summary line ends with a period, no blank line before class docstrings).

## Verification

- [ ] Every changed code example executes (`uv run python`).
- [ ] `uv run --with mkdocs-material mkdocs build --strict` — no broken-link/nav warnings.
- [ ] `just lint-ci` — clean (covers the docstring additions; `docs/` is ruff-excluded).
- [ ] `just test-ci` — full suite green (docstrings don't change behavior).

## Out of scope

- Larger restructures are kept minimal: D-6/D-9 (factories.md section reordering)
  and A-1 (containers.md lead) are done as light reorderings, not rewrites.
