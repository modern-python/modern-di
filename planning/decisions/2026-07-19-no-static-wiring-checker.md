---
status: accepted
summary: No static/compile-time wiring checker and no mypy/pyright/ty plugin; opt-in runtime validate() plus declaration-time signature parsing is the deliberate model.
supersedes: null
superseded_by: null
---

# No static / compile-time wiring checker

**Decision:** modern-di ships no static or compile-time dependency-graph checker
and no type-checker plugin (mypy, pyright, or `ty`). Whole-graph verification
stays the opt-in runtime `validate()`, backed by declaration-time signature
parsing that already fails early on an unwireable creator.

## Context

The 2026-07-19 DI static-analysis research
([audit](../audits/2026-07-19-di-static-analysis-surface-report.md)) examined how
the wider field verifies wiring *before* runtime, to decide whether modern-di
should add a static safety net — an opt-in mypy/pyright/`ty` plugin or a
richer statically-checkable API — on top of runtime `validate()`. Three verified
findings framed the call:

1. **True compile-time wiring verification exists only in compiled-language
   toolchains** — Dagger's annotation processor, Google Wire's build-time
   codegen, and Koin's K2 compiler plugin (GA June 2026). Each is a heavyweight
   toolchain, not a library artifact. Angular's headline "no provider" (NG0201)
   is a runtime error; .NET's built-in scope validation is runtime/startup;
   Spring's autowiring correctness is an IDE inspection. Runtime/startup
   validation — modern-di's `validate()` model — is the mainstream field
   standard, not a second-class fallback.
2. **Where compile-time validation exists, it is positioned as a *replacement*
   for runtime verification, not an extension.** Koin's own docs tell users they
   can delete their `verify()`/`checkModules()` tests once the compiler plugin is
   on. A static layer for modern-di would therefore duplicate `validate()`, not
   add reach beyond it.
3. **A Python type-checker plugin is infeasible for a conservative zero-dep
   library.** pyright refuses third-party plugins on principle (cross-checker
   breakage, distribution/maintenance, security of downloaded code); `ty` — the
   checker modern-di itself uses — has no plugin system (astral-sh/ty#291 closed
   "not planned"), with Astral building framework support natively instead; only
   mypy exposes a plugin API, and it is documented as experimental, with
   backwards-incompatible changes shipped without a deprecation period.

## Decision & rationale

Rejected. A static checker would, at best, **duplicate `validate()`** (finding
2) while **only serving mypy users** and carrying a **permanent maintenance
liability against an unstable, experimental plugin API** (finding 3) — and it
would not even help modern-di's own `ty` toolchain, which has no plugin seam. It
buys no reach that the opt-in runtime `validate()` (missing providers,
scope-direction violations, cycles, all-errors aggregated) plus declaration-time
`UnsupportedCreatorParameterError` does not already provide, at real cost to the
zero-dependency and conservative-feature-set constraints. Every genuine static
net in the field is a compiled-language toolchain artifact (finding 1), which a
pure-Python library cannot cheaply emulate.

The one in-constraint win the research pointed at — injection markers that
type-check to the concrete `T` — modern-di already ships: `resolve(type[T]) -> T`
and `integrations.py`'s `Annotated[T, from_di(dep)]` both preserve the concrete
static type, matching dishka's `FromDishka[T]`. That strength is documented
(comparison.md, design-decisions.md non-goals), not extended with a checker.

## Revisit trigger

`ty` (or pyright) ships a **stable, supported** third-party plugin API **and** a
concrete user-reported wiring-safety need that runtime `validate()` demonstrably
cannot meet (e.g. per-call-site checking without executing `validate()`). Both
conditions, not either alone.
