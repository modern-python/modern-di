# No static wiring checker

**Decision:** no compile-time dependency-graph checker and no type-checker plugin (mypy, pyright,
`ty`). Whole-graph verification is the opt-in runtime `validate()`, and declaration-time signature
parsing already fails early on an unwireable creator.

**Why:** true compile-time wiring verification exists only in compiled-language toolchains (Dagger,
Wire, Koin's compiler plugin), and where it exists it replaces runtime verification rather than
extending it, so a static layer here would duplicate `validate()`. A Python plugin is infeasible for
this library: pyright refuses third-party plugins, `ty` (which modern-di uses) has none, and mypy's
plugin API is experimental and changes without deprecation. The in-constraint win, injection
markers that type-check to the concrete `T`, already ships.
