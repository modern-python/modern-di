# Design decisions

The choices behind modern-di's API, and what it leaves out, so you can decide whether it fits your
project.

## 1. Resolution is sync-only; finalizers may be sync or async

`Container.resolve(...)` and `resolve_provider(...)` are synchronous, and async resolution will not
be added. There is no `await container.resolve(...)`, no `AsyncFactory` and no `AsyncSingleton`.
Async work belongs in the framework's lifespan and per-request hooks, and the container holds the
objects they built (see [Async resources via lifespan](../recipes/async-lifespan.md)). Teardown is
separate from resolution: finalizers may be sync or async (`close_sync` / `close_async`).

## 2. Cached factories are thread-safe

Each cache item, the cached instance of one `Factory` in one container, has its own reentrant lock (`threading.RLock`), so concurrent resolves in multiple threads still produce exactly one instance per cache. The lock is taken only on a cache miss; a resolve that finds the instance already cached never touches it. On a miss, the dependencies are resolved and the creator is called while the lock is held, so threads that miss together build the dependencies once, and the others wait for that instance.

### The thread-safety boundary

What modern-di guarantees:

- Two threads that race to resolve the same cached provider get one instance, and the transient
  dependencies of that provider are built once for it. Different cached providers never wait for
  each other, so a creator can hand a resolve of another cached type to a worker thread and wait
  for the result.
- Registering providers is safe while other threads register or iterate. `ProvidersRegistry`
  guards `register` and `add_providers` with its own lock and iterates over a snapshot of the
  provider dict, so it never gets corrupted or raises "dict changed size during iteration".
- Free-threaded CPython (PEP 703) is supported at `2 - Beta` and tested under real multithreading
  on the `3.14t` build. It is Beta because modern-di relies on object-publication ordering (a
  reader that sees a stored reference sees fully initialized fields), and CPython implements that
  without a published memory model to guarantee it. Per-operation latency is competitive, but
  throughput does not scale across cores: atomic reference counting of the objects every resolve
  shares keeps it close to the GIL build.

What you must do:

- Call `validate()` at startup if the graph might contain a cycle. On one thread, a cycle raises
  `CircularDependencyError` from the runtime guard. Two threads that cold-resolve different
  providers of the same cycle at once can each hold one cache item's lock while waiting for the
  other's, and block forever. A creator that waits on another thread resolving the provider it is
  creating, directly or through its dependencies, deadlocks the same way.
- Register every provider before serving. Nothing breaks if you register while other threads
  resolve, but whether a given resolve sees the new provider is undefined.
- Set overrides during setup, never from competing threads. `set_context` and overrides are
  last-write-wins: concurrent writes to the same key keep whichever landed last. Context is per
  container, so per-request context belongs on a request-local child container. Overrides live in
  one registry shared by the whole container tree, so an override set on any container is seen by
  every container in it.
- Never close one container from two places at once: no overlapping `close_async()` calls on it,
  and no `close_sync()` while a `close_async()` is still running.

## 3. No global state

All state lives in container registries: resolved instances, context values, overrides. There is no module-level container, no `current_container()`, no thread-local singleton. You explicitly create a `Container` and pass it (or its children) where it needs to go. Framework integrations handle this for you.

## 4. Typed end to end

Provider types are generic over the type they resolve, so `resolve(SomeType)` is typed `SomeType`
and an integration's `Annotated[T, from_di(dep)]` type-checks as `T`, with no type-checker plugin.
The library itself is checked with `ty` and ruff's full rule set (`select = ["ALL"]`), with four
escape hatches (`typing.cast`, `ty: ignore`) in the whole codebase.

## 5. Conservative feature set

A feature is added only when the existing primitives cannot solve the task. The core has three
concrete provider types (`Factory`, `Alias`, `ContextProvider`), plus the `AbstractProvider` base
and the pre-built `container_provider` singleton. For comparison, dependency-injector 4.49 has about
40 provider classes and that-depends about a dozen. A small core is less to learn and less to keep
correct.

The provider set is closed. `AbstractProvider` is the shared base that appears in signatures, not a hook: resolution compiles a resolver per known provider type (see
[why modern-di is fast](performance.md#why-modern-di-is-fast-here)), so defining a subclass of `AbstractProvider` or `Factory` raises `TypeError` when the class is created. Compose behaviour in a creator function or an `Alias` instead.

Caching is one argument, `Factory(cache=True | CacheSettings(...))`, rather than a `Singleton` class: a class would say "cached" in its name and again in the settings it still needs for a finalizer, and the two can drift.

## 6. Validation is explicit

`container.validate()` is the only thing that walks the graph. It checks cycles, scope ordering
and unresolvable dependencies, and reports every error it finds at once. Construction, `open()`,
`add_providers` and `resolve()` never validate: a per-resolve check would tax every resolve for a
property that matters once, at boot, and a validation hook on container setup would not run in
every execution context. Call `validate()` in a startup path or in one test. Otherwise a broken graph
surfaces at resolve time.

## 7. Errors are `RuntimeError`s

`ModernDIError`, the base of every error the library raises, subclasses `RuntimeError`, so
`except RuntimeError` catches every `modern-di` error. Code that already guards a resolve or a close
with `except RuntimeError` keeps working. Removing the base would change what those handlers catch,
and nothing would warn about it. Catch `ModernDIError` to handle only `modern-di` errors.

## 8. A small public surface

`Container(...)` builds a root and nothing else. A child comes only from
`build_child_container()`, which is the single spelling for it, and the constructor has no
`parent_container=` argument.

### Subclassing `Container`

A child of a `Container` subclass is an instance of that subclass, but `build_child_container()`
does not call its `__init__`. A subclass `__init__` cannot receive the parent, so running it for a
child would mean guessing its arguments. State that a subclass sets in `__init__` exists on the
root only.

### What is public

The public names are the ones exported by four modules: `modern_di`, `modern_di.providers`,
`modern_di.exceptions` and `modern_di.integrations`. Every other module is internal, including
the ones that define an exported name, so the code can move between modules without a major
release. See [What is public](../providers/advanced-api.md#what-is-public).

## Non-goals

These are out of scope. If you were about to request one, the reason it is out and what to do
instead are below.

### Auto-binding / auto-registration

modern-di never registers a provider for a type you did not declare and never infers wiring by scanning your code. Without it, a missing provider is an `ArgumentResolutionError`, reported by `validate()` (run it once at startup or in a test) or raised at resolve. Auto-binding would hide that error until whichever request first exercises the untested path. Register the provider in a `Group`; if the boilerplate is real, write a small helper in your application that builds several `Factory` instances from a list of classes.

### In-package framework integrations

The core package ships no framework-specific code; every integration is a separate `modern-di-*` package with its own release cadence. Bundling them would couple core's releases to every framework's churn and erode the zero-dependency guarantee. See [Writing an integration](../integrations/writing-integrations.md).

### Multibinding / collection injection

One type, one provider. Registering several providers for one type and injecting them as a `list[T]` turns the registry from a type → provider map into type → collection, which changes every operation on it: duplicate registration becomes conditional, `resolve(T)` and `resolve(list[T])` resolve different things, overriding `T` is ambiguous, and validation can no longer tell an empty collection from a wiring mistake. A `Factory` that takes the individual dependencies and returns the list costs one provider.

### Generator creators (teardown after `yield`)

`Factory` does not treat a generator creator as "yield the value, run the rest as a finalizer"; `CacheSettings(finalizer=)` is the only teardown spelling. Under sync resolution a generator cannot express an async finalizer, which the explicit form can, and a generator creator currently resolves to the generator itself, so the change would break existing code. Write a plain creator that returns the value and pass the teardown as `Factory(..., cache=CacheSettings(finalizer=...))`.

### An `enter_scope` alias for `build_child_container`

Peers name scope entry by intent (`enter_scope`, `CreateScope`); modern-di names the mechanism, because here the mechanism is the concept: a child container is a real object with its own cache and context, and "entering a scope" would hide that model. One spelling for the most-written call after `resolve()`: use `build_child_container()`.

### Resolution tracing / logging

No `logging.getLogger("modern_di")` narrating resolution. The guard alone (`isEnabledFor(DEBUG)`) measured about 19 ns, roughly 10x a bare boolean, and a cached factory needs two; patched into the resolvers with tracing *off* it cost +37% on a warm cached hit and +31% on a by-type resolve, paid by every user for a feature they never enable. A compile-time gate would be free but adds a second activation API. Diagnostics are the job of the error messages, which carry the resolution chain at no hot-path cost.

### Graph rendering / visualization tooling

No built-in way to render the dependency graph as a picture. Rendering is a standalone subsystem rather than an extension of an existing primitive, so it sits outside the conservative feature set and the zero-dependency guarantee. Walk `Group.get_providers()` yourself and feed the edges to the diagram tool of your choice.

### Static / compile-time wiring verification (a type-checker plugin)

No static dependency-graph checker and no type-checker plugin. True compile-time wiring checks are a property of compiled-language toolchains (Dagger, Wire, Koin's compiler plugin), and where they exist they replace runtime verification rather than extend it. A Python plugin is infeasible here: pyright supports no third-party plugins, `ty` (which modern-di uses) has none, and mypy's plugin API is experimental. Call [`validate()`](../providers/lifecycle.md) in a startup path or a single test; it works identically under every checker.

## See also

- [About DI](about-di.md): the framework-agnostic introduction.
- [Comparison](comparison.md): what other libraries do where modern-di says no.
- [Migration from `that-depends`](../migration/from-that-depends.md): what these decisions changed compared to the older framework.
