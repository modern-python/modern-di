---
summary: Runtime cycle guard (ERR-1): an unvalidated circular graph raises CircularDependencyError with the cycle path instead of a raw RecursionError.
---

# Design: Runtime cycle guard

## Summary

Implements shortlist ruling ERR-1/API-7 (2026-07-05 UX research, amended
sketch). Today an unvalidated circular graph dies with a bare `RecursionError`
on first resolve — the field's worst-cited bug class (dependency-injector
#811, injector's resolve-time detection is the precedent). After this change,
`Container.resolve_provider` catches an escaping `RecursionError`, re-walks
the static graph **iteratively** from the failing provider, and — if a static
cycle is reachable — raises `CircularDependencyError(cycle_path=...)`
`from` the original. If no static cycle exists (a user creator recursing on
its own), the original `RecursionError` is re-raised untouched.

## Design

- **Iterative cycle finder.** A module-private helper (in
  `modern_di/container.py` or a small new module): explicit-stack DFS from
  one provider over `provider.get_dependencies(container)`
  (abstract.py:40 — pure registry lookup, no cache/context), returning the
  cycle as `list[str]` of `display_name`s (first name repeated at the end,
  matching `validate()`'s format at container.py:191-194) or `None`.
  Iterative is a hard requirement: the handler runs at maximum stack depth,
  where `validate()`'s recursive `_visit` cannot.
- **The guard.** In `resolve_provider` (container.py:168), wrap the final
  `provider.resolve(self)` in `try/except RecursionError`. On catch: run the
  finder from `provider`; cycle → `raise CircularDependencyError(cycle_path=cycle)
  from exc`; no cycle → bare `raise`. `resolve_provider` is re-entrant
  (Factory/Alias call it per dependency edge), so the innermost frame
  converts; outer frames see a `ResolutionError` and the existing breadcrumb
  machinery prepends steps — the converted error arrives with the full
  dependency chain for free.
- **`validate()` unchanged.** Deliberate duplication of cycle detection:
  `validate()` collects all errors of all kinds in one recursive walk; the
  helper answers one reachability query on an exhausted stack. Unifying them
  would couple the hot error path to the all-errors walker for no user gain.
- **Zero happy-path cost**: one `try/except` (zero-cost on 3.11+).

## Non-goals

- No per-resolve in-flight bookkeeping (option (b) in the report) — rejected
  for hot-path cost; the static re-walk gives the same answer for static
  cycles.
- No change to `CircularDependencyError`'s constructor or rendering (the
  arrow chain shipped in 2.24.0 work).
- Not a 3.0 switch: this replaces a documented crash, non-breaking.

## Docs (same PR)

- `architecture/validation.md`: rewrite the "runtime resolution has no cycle
  guard" note (it now has one; validate() remains the way to see all errors
  before first resolve).
- `docs/providers/errors-and-exceptions.md`: `CircularDependencyError` is
  raised by `validate()` and by the runtime guard; `RecursionError` remains
  only for genuinely recursive user creators.
- `docs/troubleshooting/circular-dependency.md`: update the "what you see
  without validation" framing.

## Testing

TDD:
- Unvalidated cyclic graph (A→B→A): first `resolve` raises
  `CircularDependencyError`; `cycle_path` correct; `__cause__` is the
  `RecursionError`.
- Deep chain variant: cycle not adjacent to the resolve root (root → X → A→B→A)
  — converted error carries breadcrumbs naming the chain.
- Self-recursing creator in a valid graph: original `RecursionError`
  re-raised (no conversion), `CircularDependencyError` absent.
- `validate=True` path unaffected (existing tests).
- Gates: `just test-ci` (100%), `just lint-ci`, `just docs-build`.

## Risk

- **Headroom in the handler** (low/medium): CPython allows work in a
  `RecursionError` handler as frames have unwound to the catch site, but the
  innermost frame sits near the limit — the finder must stay iterative and
  flat (no recursion, minimal call depth). The deep-chain test exercises
  exactly this.
- **False conversion** (low/low): a creator that recurses AND whose graph has
  an unrelated static cycle would be attributed to the cycle. Acceptable: the
  graph does contain a real cycle the user must fix; `__cause__` preserves
  the original.
