# Design decisions

`modern-di` is opinionated. These are the deliberate choices behind the API so you can decide whether the framework matches your project.

## 1. Resolution is sync-only; finalizers may be sync or async

Since 2.x, `Container.resolve(...)` and `resolve_provider(...)` are synchronous. There is no `await container.resolve(...)`, no `AsyncFactory`, no `AsyncSingleton`. Async work belongs in the framework's lifespan and per-request hooks; the container holds the already-constructed objects (see [Async resources via lifespan](../recipes/async-lifespan.md)). Resolution being sync does not mean teardown is: finalizers may be sync or async (`close_sync` / `close_async`), so async cleanup is fully supported.

This is a permanent choice, not a temporary limitation. There are no plans to reintroduce async resolution.

## 2. Cached factories are thread-safe

Cached `Factory` providers use a per-container reentrant lock (`threading.RLock`) so concurrent resolves in multiple threads still produce exactly one instance per cache. Single-threaded apps can disable the lock with `Container(..., use_lock=False)` for a small performance gain; multi-threaded apps must leave it on.

### The thread-safety boundary

- **Cached / singleton creation is locked.** The per-container reentrant lock guards the create-and-store step, so two threads racing to resolve the same cached provider get the same single instance.
- **Provider registration is safe.** `ProvidersRegistry` mutations (`register`, `add_providers`) are guarded by the registry's own lock, and iteration snapshots the provider dict (`iter(list(...))`), so registering providers concurrently — or while another thread iterates — will not corrupt the registry or raise "dict changed size during iteration".
- **Registration is a setup phase, not a coordination tool.** The registry is
  lock-guarded against corruption, but the supported model is register every
  provider *before* serving. Registering a provider while other threads are
  already resolving is timing-dependent by nature — nothing breaks, but whether
  a given resolve sees the new provider is undefined.
- **`set_context` and overrides are last-write-wins.** Both write into a
  per-container dict with no ordering, queueing, or merge; concurrent writes to
  the same key keep whichever landed last. Do them during setup, or per-request
  on a request-local child container — never from competing threads.
- **Free-threaded CPython (PEP 703) is supported at `2 - Beta`.** Production-ready
  and tested under real multithreading on the `3.14t` build. It is Beta rather than
  Stable for one specific reason: modern-di relies on object-publication ordering —
  that a reader observing a stored reference sees fully-initialized fields — and
  CPython publishes no memory model, so that is implementation behaviour rather than
  a spec guarantee. Throughput also does not scale across cores; per-op latency is
  competitive, but atomic reference counting of the objects every resolve shares
  tracks the GIL.

## 3. No global state

All state — resolved instances, context values, overrides — lives in container registries. There is no module-level container, no `current_container()`, no thread-local singleton. You explicitly create a `Container` and pass it (or its children) where it needs to go. Framework integrations handle this for you.

## 4. Maximum type safety

The codebase is type-checked with `ty` and linted with ruff's full rule set (`select = ["ALL"]`). Escape hatches (`typing.cast`, `ty: ignore`) are rare and localized — a handful across the whole library. Provider types parameterize on the resolved type, so type checkers infer the right thing without help.

## 5. Conservative feature set

New features get added only when existing primitives genuinely cannot solve the task. The core has three concrete provider types (`Factory`, `Alias`, `ContextProvider`), plus the `AbstractProvider` base and the pre-built `container_provider` singleton — most other DI frameworks have two to three times that. This is deliberate: a small, composable core is easier to learn, easier to test, and easier to keep correct.

The provider set is closed. `AbstractProvider` is the shared base that appears in signatures, not a hook: resolution compiles a resolver per known provider type, so a subclass of `AbstractProvider` or `Factory` raises `TypeError` at its first resolve. Compose behaviour in a creator function or an `Alias` instead.

Caching is one argument, `Factory(cache=True | CacheSettings(...))`, rather than a `Singleton` class: a class would say "cached" in its name and again in the settings it still needs for a finalizer, and the two can drift.

## 6. Validation is explicit

`container.validate()` is the only thing that walks the graph. Construction, `open()`, `add_providers` and `resolve()` never validate. 3.0 tied validation to a mandatory `open()`, and that produced six production defects with one root cause (the root's open hook does not fire in every execution context) plus an ordering rule that existed only because of the binding. An implicit scheme was built and discarded for the machinery it needed; a per-resolve check would tax the hot path for a property that matters once, at boot. The cost is that a broken graph surfaces from an explicit `validate()` or at resolve time.

## Non-goals

Beyond the choices above, these are deliberately out of scope. Naming them here is meant to save you from filing (or us from re-litigating) the same request.

### Auto-binding / auto-registration

modern-di never registers a provider for a type you did not declare and never infers wiring by scanning your code. Auto-binding defers a missing-provider error from declaration time, where `UnsupportedCreatorParameterError` already raises, to whichever request first exercises the untested path. Register the provider in a `Group`; if the boilerplate is real, a small helper that builds several `Factory` instances from a list of classes is application code, not a framework feature.

### In-package framework integrations

The core package ships no framework-specific code; every integration is a separate `modern-di-*` package with its own release cadence. Bundling them would couple core's releases to every framework's churn and erode the zero-dependency guarantee. See [Writing an integration](../integrations/writing-integrations.md).

### Multibinding / collection injection

One type, one provider. Registering several providers for one type and injecting them as a `list[T]` turns the registry from a type → provider map into type → collection, which changes every operation on it: duplicate registration becomes conditional, `resolve(T)` and `resolve(list[T])` resolve different things, overriding `T` is ambiguous, and validation can no longer tell an empty collection from a wiring mistake. A `Factory` that takes the individual dependencies and returns the list costs one provider.

### Generator creators (teardown after `yield`)

`Factory` does not treat a generator creator as "yield the value, run the rest as a finalizer"; `CacheSettings(finalizer=)` is the only teardown spelling. The generator form is breaking (a generator creator resolves to the generator today), needs per-instance finalizer records for uncached factories and `bound_type` extraction from `Iterator[T]`, and cannot express an async finalizer under sync resolution, which the explicit form can. A `Factory` subclass in application code can wrap a generator creator and register the continuation as a finalizer.

### An `enter_scope` alias for `build_child_container`

Peers name scope entry by intent (`enter_scope`, `CreateScope`); modern-di names the mechanism, because here the mechanism is the concept: a child container is a real object with its own cache and context, and "entering a scope" would hide that model. One spelling for the most-written call after `resolve()`.

### Resolution tracing / logging

No `logging.getLogger("modern_di")` narrating resolution. The guard alone (`isEnabledFor(DEBUG)`) measured about 19 ns, roughly 10x a bare boolean, and a cached factory needs two; patched into the resolvers with tracing *off* it cost +37% on a warm cached hit and +31% on a by-type resolve, paid by every user for a feature they never enable. A compile-time gate would be free but adds a second activation API. Diagnostics are the job of the error messages, which carry the resolution chain at no hot-path cost.

### Graph rendering / visualization tooling

No built-in way to render the dependency graph as a picture. Rendering is a standalone subsystem rather than an extension of an existing primitive, so it sits outside the conservative feature set and the zero-dependency guarantee. Walk `Group.get_providers()` yourself and feed the edges to the diagram tool of your choice.

### Static / compile-time wiring verification (a type-checker plugin)

No static dependency-graph checker and no type-checker plugin. True compile-time wiring checks are a property of compiled-language toolchains (Dagger, Wire, Koin's compiler plugin), and where they exist they replace runtime verification rather than extend it. A Python plugin is infeasible here: pyright supports no third-party plugins, `ty` (which modern-di uses) has none, and mypy's plugin API is experimental. Call [`validate()`](../providers/lifecycle.md) in a startup path or a single test; it works identically under every checker.

## See also

- [About DI](about-di.md) — the framework-agnostic introduction.
- [Migration from `that-depends`](../migration/from-that-depends.md) — what these decisions changed compared to the older framework.
