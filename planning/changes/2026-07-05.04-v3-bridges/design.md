---
summary: 2.x bridges for the ruled 3.0 breaks — validation report rework, tri-state validate FutureWarning, ContextProvider unset-value DeprecationWarning, and the to-3.x migration guide.
---

# Design: 3.0 bridges on 2.x (validation UX, ContextProvider deprecation, migration guide)

## Summary

Implements the 2.x-shippable half of the 3.0-gated trio ruled in the
[2026-07-05 UX research](../../audits/2026-07-05-v3-ux-research-report.md)
(API-1/ERR-2, ERR-5, API-6, DOC-1) under the agreed strategy: bridge warnings
on 2.x now, all breaking flips deferred to a single cut-3.0 bundle before the
tag. Four pieces: (1) rework the rendering of `ValidationFailedError` and
`CircularDependencyError`; (2) a tri-state `validate` parameter whose unset
state emits a `FutureWarning` on root containers; (3) a `DeprecationWarning`
when an unset `ContextProvider` is resolved directly, plus the
`ContextValueNotSetError` class it becomes in 3.0; (4) `docs/migration/to-3.x.md`
covering all five 3.0 switches with a warnings-as-errors readiness recipe.

## Motivation

Rulings API-1/ERR-2 (validate default-on in 3.0) and API-6 (raise on unset
ContextProvider in 3.0) are breaking; the house pattern for breaks
(`ContainerClosedWarning` → `ContainerClosedError`) is to warn one cycle ahead
so `filterwarnings("error")` turns a green 2.x suite into a 3.0 guarantee.
ERR-5 matters now because once validation is on by default, its report is the
first thing users see on a broken graph — and the current flat rendering
mangles multi-line sub-errors. DOC-1 is time-boxed: it must exist before the
3.0 tag, and it can only be complete once these two bridge warnings exist.

## Non-goals

- No behavior flips: `validate` still defaults to off-behavior; unset
  ContextProvider still returns `None`. Flips happen in the cut-3.0 bundle.
- No changes to dependent-parameter context dispositions (default/nullable/
  raise) — they go through `fetch_context_value`, not `ContextProvider.resolve`.
- No `validate()` content changes — only rendering (`__str__`) of the two
  exception classes.
- The INT-1 interaction (post-construction `add_providers` vs.
  validate-at-construction) is a cut-3.0 design question, recorded there, not
  solved here.

## Design

### 1. ERR-5 — validation report rendering

`ValidationFailedError.__str__` currently renders a count header plus flat
`  - {e}` lines (exceptions.py:364-367), which mangles multi-line sub-errors
(e.g. "Did you mean" suggestion blocks). Rework, rendering only:

- Group `.errors` by exception class; per-group header
  `CircularDependencyError (2):` ordered by class name; items indented under
  their group with continuation lines indented to match (`textwrap.indent`-style).
- `CircularDependencyError.__str__` renders `cycle_path` as a multi-line arrow
  chain consistent with the existing `ResolutionError` breadcrumb style
  (`└─>` continuation lines), replacing the inline `A -> B -> A` string.
  `cycle_path` attribute stays `list[str]`.
- `.errors` list, exception types, and the one-line summary header (used by
  `repr`/logging) keep their current content.

### 2. API-1 bridge — tri-state `validate`

`Container.__init__` signature changes `validate: bool = False` →
`validate: bool | None = None`:

- `None` (unset) on a **root** container (`parent_container is None`): emit
  `UnvalidatedContainerWarning` (new, subclass of `FutureWarning`, in
  `exceptions.py`) — "modern-di 3.0 runs validate() at root construction by
  default; pass validate=True to adopt now, or validate=False to keep opt-out"
  — then behave as today (no validation). Python's default warning filter
  dedupes by raise site, so it fires effectively once per process.
- `None` on a child: no warning, no validation (children never validate;
  `build_child_container` does not pass `validate`, so this is the automatic
  path).
- Explicit `False`: no warning ever — a conscious opt-out stays valid after
  the 3.0 flip.
- Explicit `True`: validates, as today.

`FutureWarning` (not `DeprecationWarning`) because it is a behavior change
addressed to app authors — shown by default. Docstring carries the escalation
recipe, mirroring `ContainerClosedWarning`.

### 3. API-6 bridge — ContextProvider unset-value deprecation

Mirroring the `ContainerClosedWarning`/`ContainerClosedError` pair:

- New `ContextValueNoneWarning(DeprecationWarning)` in `exceptions.py`, with
  the escalation recipe in its docstring.
- New `ContextValueNotSetError(ResolutionError)` in `exceptions.py`, not
  raised anywhere in 2.x; docstring states it is raised by modern-di 3.0 when
  an unset `ContextProvider` is resolved directly. Message (built in
  `__init__`, inline f-string per house style) names the context type and
  scope with remedy text "pass context={T: value} to the container or call
  set_context()".
- `ContextProvider.resolve`: when `fetch_context_value` returns `UNSET`, emit
  `ContextValueNoneWarning` naming the context type, then return `None` as
  today. The warning message points at the 3.0 error and the migration guide.

### 4. DOC-1 — `docs/migration/to-3.x.md`

New page in the existing `docs/migration/` set (sibling of to-1.x/to-2.x),
covering all five 3.0 switches:

| Switch | 2.x signal |
|---|---|
| Closed-container reuse raises `ContainerClosedError` | `ContainerClosedWarning` |
| `Alias(scope=)` removed | `DeprecationWarning` |
| `Factory(cache_settings=)` removed | `DeprecationWarning` |
| `validate()` default-on at root construction | `UnvalidatedContainerWarning` (this bundle) |
| Unset `ContextProvider` direct resolve raises `ContextValueNotSetError` | `ContextValueNoneWarning` (this bundle) |

Structure: switch table with before/after code per break; readiness recipe —
a `filterwarnings` block escalating all five warning signals so a green 2.x
suite guarantees a clean 3.0 upgrade; the stated deprecation policy (warn one
cycle, remove/flip at the major). The two new warnings' docstrings and the
mkdocs nav link to it.

## Testing

TDD (failing test first per task):

- Rendering: unit tests asserting grouped/indented `ValidationFailedError`
  output including a multi-line sub-error, and the `CircularDependencyError`
  arrow chain.
- `UnvalidatedContainerWarning`: fires on unset root; absent for explicit
  `True`/`False`; absent on children; escalatable via
  `filterwarnings("error")`.
- `ContextValueNoneWarning`: fires on direct resolve of unset value (returns
  `None`); absent when value is set; dependent-parameter paths unchanged
  (existing tests must stay green without modification); escalatable.
- Existing suite: the repo's own pytest config gains a
  `filterwarnings = ["ignore::modern_di.exceptions.UnvalidatedContainerWarning"]`
  entry (166 root constructions in tests would otherwise each warn); the
  targeted warning tests override it via `pytest.warns`/`catch_warnings`.
- Gates: `just test-ci` (100% coverage), `just lint-ci`, docs build via the
  strict-links CI job.

## Risk

- **Warning noise downstream** (high likelihood, low harm — by design): every
  2.x user constructing a root without `validate=` sees one FutureWarning per
  process. Mitigated: one-kwarg remedy stated in the message; explicit `False`
  silences permanently.
- **Test-suite churn** (medium/low): repo tests construct many root
  containers. Mitigated: a shared helper/explicit args pass; the diff stays
  mechanical.
- **Docs drift** (low/medium): to-3.x.md promises five flips the cut-3.0
  bundle must deliver exactly. Mitigated: the cut-3.0 bundle references this
  table as its checklist.
