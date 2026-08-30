# No static / compile-time wiring checker

**Decision:** modern-di ships no static or compile-time dependency-graph checker and no type-checker
plugin (mypy, pyright, or `ty`). Whole-graph verification stays the opt-in runtime `validate()`,
backed by declaration-time signature parsing that already fails early on an unwireable creator.

Three verified findings decide it:

1. **True compile-time wiring verification exists only in compiled-language toolchains** — Dagger's
   annotation processor, Google Wire's build-time codegen, Koin's K2 compiler plugin (GA June 2026).
   Angular's "no provider" (NG0201) is a runtime error, .NET's scope validation is runtime/startup,
   Spring's autowiring correctness is an IDE inspection. Runtime/startup validation is the
   mainstream field standard, not a second-class fallback.
2. **Where compile-time validation exists, it *replaces* runtime verification rather than extending
   it** — Koin's own docs tell users to delete their `verify()`/`checkModules()` tests once the
   plugin is on. A static layer here would duplicate `validate()`, not reach past it.
3. **A Python type-checker plugin is infeasible for a conservative zero-dep library.** pyright
   refuses third-party plugins on principle; `ty` — the checker modern-di itself uses — has no
   plugin system (astral-sh/ty#291 closed "not planned"); only mypy exposes a plugin API, documented
   as experimental with backwards-incompatible changes shipped without a deprecation period.

So a checker would duplicate `validate()`, serve mypy users only, carry a permanent liability
against an unstable API, and not even help modern-di's own `ty` toolchain. The one in-constraint win
the research pointed at — injection markers that type-check to the concrete `T` — already ships:
`resolve(type[T]) -> T` and `Annotated[T, from_di(dep)]` both preserve the concrete static type.

**Revisit trigger:** `ty` (or pyright) ships a **stable, supported** third-party plugin API **and** a
concrete user-reported wiring-safety need that runtime `validate()` demonstrably cannot meet (e.g.
per-call-site checking without executing `validate()`). Both conditions, not either alone.
