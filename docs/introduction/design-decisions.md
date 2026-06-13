# Design decisions

`modern-di` is opinionated. These are the deliberate choices behind the API so you can decide whether the framework matches your project.

## 1. Resolution is sync only

Since 2.x, `Container.resolve(...)` and `resolve_provider(...)` are synchronous. There is no `await container.resolve(...)`, no `AsyncFactory`, no `AsyncSingleton`. Async work belongs in the framework's lifespan and per-request hooks; the container holds the already-constructed objects (see [Async resources via lifespan](../recipes/async-lifespan.md)).

This is a permanent choice, not a temporary limitation. There are no plans to reintroduce async resolution.

## 2. Cached factories are thread-safe

Cached `Factory` providers use a `threading.Lock` so concurrent resolves in multiple threads still produce exactly one instance per cache. Single-threaded apps can disable the lock with `Container(..., use_lock=False)` for a small performance gain; multi-threaded apps must leave it on.

## 3. No global state

All state — resolved instances, context values, overrides — lives in container registries. There is no module-level container, no `current_container()`, no thread-local singleton. You explicitly create a `Container` and pass it (or its children) where it needs to go. Framework integrations handle this for you.

## 4. Maximum type safety

The codebase is type-checked with `ty` and linted with ruff's full rule set (`select = ["ALL"]`). Escape hatches (`typing.cast`, `ty: ignore`) are rare and localized — a handful across the whole library. Provider types parameterize on the resolved type, so type checkers infer the right thing without help.

## 5. Conservative feature set

New features get added only when existing primitives genuinely cannot solve the task. The core has five providers (`Factory`, `Alias`, `ContextProvider`, `container_provider`, `AbstractProvider`) — most other DI frameworks have two to three times that. This is deliberate: a small, composable core is easier to learn, easier to test, and easier to keep correct.

## See also

- [About DI](about-di.md) — the framework-agnostic introduction.
- [Migration from `that-depends`](../migration/from-that-depends.md) — what these decisions changed compared to the older framework.
