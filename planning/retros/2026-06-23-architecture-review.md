# Retro — architecture review, three deepenings, and the decisions lane (2026-06-23)

One session: an architecture review (4 candidates) → 3 deepening refactors
shipped (`WiringPlan` #226, inline error messages #227, `suggester` #228) +
1 declined on record (close stack) → a `decisions/` convention → release 2.19.1.

## What worked

- **Grilling corrected the review's premises before any code was written — 3 of 4
  times.** The HTML report's framings were hypotheses, not ground truth:
  - #1's "compute the plan once per provider" was *unsafe* — the same `Factory`
    is registered into many registries across the test suite. Caught by exploring
    the suite during grilling, before it shipped a cross-registry bug.
  - #2's premise that a shared suggestion constant forces a neutral home (and an
    import cycle) was *false* — no constant actually crossed both modules, so
    `errors.py` could be deleted outright, not merely slimmed.
  - #4's "six near-identical methods" was misleading — only one layer was;
    `CacheItem`/`CacheRegistry` diverge intrinsically (sync can't `await`).
    Investigation flipped the call from "do it" to "don't."
  - **Takeaway:** treat architecture-review output as hypotheses to verify against
    the real code. The design happens in the grilling, not the report.

- **The whole-branch review on the most capable model earned its cost.** #1's
  review found a CRITICAL breadcrumb-mutation bug — a memoized, mutable
  `ArgumentResolutionError` that `prepend_step` compounded across repeated/nested
  failing resolves. **Invisible to 100% coverage** because no test resolved the
  same failing provider twice. The fix (store records, build errors fresh) was a
  genuine design improvement, not a patch.
  - **Takeaway:** coverage proves a line *runs*, not that behavior is correct
    under repetition. Spend the capable-model review on hot-path / error-handling
    refactors.

- **Verification caught what greps and tests missed.** `ty` flagged a third
  `errors` importer (a benchmark) that the initial grep overlooked. For the
  text-preserving #2, a before/after `str(e)` dump across all 23 exceptions was
  the real guard — coverage can't prove byte-identical messages.

- **Model tiering in SDD paid off** — cheap models for mechanical inlining,
  capable for the core rewires, opus for the final reviews.

## What was bumpy

- **A stale `.claude/worktrees/` copy polluted `ty check` the entire session.** I
  worked around it (scoping `ty` to deliverable dirs) every single time instead
  of removing it at first encounter. **Fix environment quirks when first hit, not
  on the Nth workaround.**
- **A fix subagent force-committed scratch** (`.superpowers/sdd/*-report.md`) into
  a commit; caught and stripped via amend. Subagents committing
  globally-ignored scratch is a footgun — **verify commit contents when a
  subagent commits.**
- **Convention churn on the decisions lane**: flat log → compact entries →
  file-per-decision, across three rounds of feedback in one PR. Iterating is fine,
  but the single-file-vs-files question was answerable upfront; defaulting to flat
  then reversing cost a couple of cycles. **Ask the structural question first when
  it's foreseeable.**
- **RTK grep mangling** ("N matches in 0 files") recurred and silently dropped
  output a few times — re-run as plain grep when results look wrong.

## Carry forward

- Architecture-review candidates are hypotheses; budget grilling/investigation to
  confirm or flip each before committing to a build.
- For behavior-preserving refactors, write the explicit before/after output diff
  (messages, results) as the migration guard — not just the test suite.
- The `decisions/` lane exists now: when a candidate is *declined* with a
  load-bearing reason, record it (it stopped #4 from being re-suggested).
