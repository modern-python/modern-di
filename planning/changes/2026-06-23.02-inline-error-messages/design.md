---
status: draft
date: 2026-06-23
slug: inline-error-messages
summary: Inline the single-use error templates into their exception classes and delete the errors.py seam.
supersedes: null
superseded_by: null
pr: null
outcome: null
---

# Design: Inline error messages into their exceptions and delete `errors.py`

## Summary

`modern_di/errors.py` is a module of 21 message-template constants. **Nineteen of
them are referenced exactly once, by exactly one consumer** — a 1:1 indirection
that forces a cross-file bounce to read any one error. This change inlines each
single-use template as an f-string in the exact `__init__` that raises it
(locality: the message lives with its raise), relocates the small suggestion
vocabulary to the two modules that actually use it, and **deletes `errors.py`**.
It is a pure refactor: every rendered message stays byte-identical.

## Motivation

From the 2026-06-23 architecture review (candidate 2, "delete the `errors.py`
seam"). `errors.py` is internal-only — not exported from `modern_di/__init__.py`,
not referenced by docs — and is imported by exactly two modules: `exceptions.py`
and `registries/providers_registry.py`. Of its 21 constants, 19 are used once in
one place; the `.format()` call is the only thing wrapping the literal. The
**deletion test**: inlining concentrates each message into the single `__init__`
that builds it — complexity moves home, it does not multiply. The seam carries no
variation, so it is not earning its keep.

The review flagged one risk: if the suggestion vocabulary were shared *across*
both modules, `errors.py` would be a legitimate dependency-free home (deleting it
would risk an `exceptions ↔ providers_registry` import cycle). **Verified false:**
no single constant crosses both modules. `SUGGESTION_HEADER` is used only in
`exceptions.py` (two classes); `SUGGESTION_SUBCLASS`/`BASECLASS`/`SIMILAR` are
used only in `providers_registry.py`. Each constant's true home is the one module
that uses it, so `errors.py` can be removed entirely with no cycle.

## Non-goals

- **Unifying the suggestion vocabulary (candidate 3).** The "did you mean" block
  is already assembled across two modules today — `providers_registry` formats the
  lines, `exceptions` prepends the header. This change preserves that exact split;
  consolidating it into a `suggester` module is candidate 3's job.
- **Touching the dynamically-built messages.** `UnknownFactoryKwargError`,
  `ValidationFailedError`, and `FinalizerError` already build their messages inline
  without an `errors.py` template — they are unchanged.
- **Adding permanent message-snapshot tests.** Brittle and low-value; the existing
  `match=` tests plus a one-time before/after diff (see Testing) are the guard.

## Design

### 1. Inline the single-use templates into their exception classes

For each of the 17 templates used by exactly one `exceptions.py` class, replace
`super().__init__(errors.X.format(...))` with an f-string literal in that
`__init__`. The values interpolated are already locals there (`scope.name`,
`repr(...)`, `" | ".join(...)`, etc.), so the `.format()` layer disappears too.
Multi-line messages (e.g. the duplicate-type help block, the skipped-scope
message) keep their current shape via parenthesized implicit string
concatenation, exactly as `errors.py` spells them today. The rendered text is
preserved verbatim. Affected classes: `InvalidChildScopeError`,
`MaxScopeReachedError`, `ScopeNotInitializedError`, `ScopeSkippedError`,
`InvalidScopeTypeError`, `ContainerClosedError`, `ProviderNotRegisteredError`,
`AliasSourceNotRegisteredError`, `ArgumentResolutionError` (both branches +
unannotated), `CreatorCallError`, `CircularDependencyError`,
`DuplicateProviderTypeError`, `UnsupportedCreatorParameterError`,
`InvalidScopeDependencyError`, `AsyncFinalizerInSyncCloseError`,
`GroupInstantiationError`.

### 2. `SUGGESTION_HEADER` → a module-level constant in `exceptions.py`

`SUGGESTION_HEADER` (`"Did you mean:"`) is used by two `exceptions.py` classes
(`ProviderNotRegisteredError`, `ArgumentResolutionError`) to render the
suggestions block. It is a genuinely-shared (two-user) constant, so it becomes a
module-level constant at the top of `exceptions.py`. The two block-assembly sites
(`message += "\n" + SUGGESTION_HEADER + "\n" + "\n".join(self.suggestions)`) are
left as-is — they keep referencing the local constant.

### 3. Suggestion line-formats → inlined into `providers_registry.py`

`SUGGESTION_SUBCLASS`, `SUGGESTION_BASECLASS`, and `SUGGESTION_SIMILAR` are each
used once, in `providers_registry.py` (`_hierarchy_hint` and `build_suggestions`).
Inline them as f-strings at those call sites, preserving the exact line format
(`"  - {type_name} (registered subclass, scope={scope})"`, etc.).

### 4. Delete `errors.py`

With every constant relocated, `modern_di/errors.py` is removed and the
`from modern_di import errors` import is dropped from `exceptions.py` and from
`providers_registry.py` (which keeps its `exceptions`/`types` imports). Update the
`modern_di/errors.py` "Key files" entry in `CLAUDE.md` (remove it) and any
`architecture/` reference to `errors.py`.

## Testing

This is a pure refactor — every existing test passes **unchanged** (tests match on
message *text* via `pytest.raises(match=...)`; none import the `errors` constants).

The byte-identical guard is a **one-time before/after message dump**: a throwaway
script constructs every concrete exception class with representative args and
prints `str(e)`; run it on `main` and on the branch and `diff` — zero diff proves
no message drifted (the suite alone is insufficient, since 100% coverage
guarantees each `__init__` *runs*, not that its text is unchanged). Then `just
test-ci` green at 100% coverage and `just lint-ci` clean.

On ship, no `architecture/` capability prose changes (error *behavior* is
unchanged); only the `CLAUDE.md` key-files list and any stray `errors.py` mention
are corrected.

## Risk

- **A message drifts during inlining** — *medium likelihood / low impact, fully
  caught.* The before/after `str(e)` diff across all exception classes is the
  definitive guard; nothing merges with a non-empty diff.
- **A missed `errors.X` reference** — *low.* Only two modules import `errors`;
  after inlining, `grep -rn "errors\." modern_di` plus the dropped imports confirm
  zero remaining references before the file is deleted; `ty`/`ruff` would also flag
  an undefined name.
- **Import cycle from relocating a shared constant** — *none.* Verified no
  constant crosses both modules (see Motivation); each moves to its sole consumer.
