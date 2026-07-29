---
summary: `architecture/resolution.md` narrates `resolver_compiler.py` step by step across ~2400 words — the fastest-rotting text in the repo, because it drifts against code rather than against another document.
---

# `architecture/resolution.md` narrates implementation, so it rots against code

`architecture/resolution.md` is roughly 2400 words describing the resolve path in
sequence: "Compiled resolvers", "Per-node shape", "Step 4 — Wiring plan",
"Step 5 — Recursive resolution", "Step 6 — Creator call and caching".

## Why it is open

Every other capability page states rules and invariants; this one states *steps*.
That makes it the only page whose correctness is coupled to the current shape of
a specific module rather than to the behaviour the library promises. When
`resolver_compiler.py` is restructured, the page is wrong immediately and silently
— nothing fails, no test catches it, and the promotion rule only prompts an edit
when someone notices the page covers what they changed.

This was surfaced while deciding whether `architecture/` and `docs/` duplicate
each other. They do not — `architecture/` is mechanism, `docs/` is usage, and
where they touch it is restatement at different altitude. But the comparison made
clear that `architecture/`'s real drift risk was never against `docs/`; it is
against the code, and it is concentrated in this one page.

Two candidate fixes:

1. **Thin it to invariants.** State what must stay true (the per-node frame
   budget, cycle-safe compilation, where the override guard sits) rather than what
   the code does in order. Invariants survive refactors; step-by-step narration
   does not.
2. **Pin it with a test.** Keep the narration but make it enforceable, the way
   `tests/test_docs_slug_census.py` pins the error-page mapping.

Option 1 is cheaper and matches how the other capability pages already read.
Option 2 preserves more detail but adds a test that must itself be maintained.

## Revisit trigger

The next change that alters `resolver_compiler.py`'s shape — fix the page as part
of that change rather than re-narrating the new steps. Or the first time the page
is found to be wrong, which is the signal that narration has already failed.
