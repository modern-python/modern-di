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

## 3. No global state

All state — resolved instances, context values, overrides — lives in container registries. There is no module-level container, no `current_container()`, no thread-local singleton. You explicitly create a `Container` and pass it (or its children) where it needs to go. Framework integrations handle this for you.

## 4. Maximum type safety

The codebase is type-checked with `ty` and linted with ruff's full rule set (`select = ["ALL"]`). Escape hatches (`typing.cast`, `ty: ignore`) are rare and localized — a handful across the whole library. Provider types parameterize on the resolved type, so type checkers infer the right thing without help.

## 5. Conservative feature set

New features get added only when existing primitives genuinely cannot solve the task. The core has three concrete provider types (`Factory`, `Alias`, `ContextProvider`), plus the `AbstractProvider` base and the pre-built `container_provider` singleton — most other DI frameworks have two to three times that. This is deliberate: a small, composable core is easier to learn, easier to test, and easier to keep correct.

## Non-goals

Beyond the choices above, three more things are deliberately out of scope. Naming them here is meant to save you from filing (or us from re-litigating) the same feature request.

### Auto-binding / auto-registration

**What:** modern-di never registers a provider for a type you didn't declare, and never infers wiring by scanning your codebase (import scanning, decorator scanning, `auto_bind`-style fallbacks some frameworks offer).

**Why:** Auto-binding defers a missing-provider error from declaration time — where modern-di already raises `UnsupportedCreatorParameterError` — to whichever request first exercises the untested path. That's the opposite of the framework's declaration-time-failure bet, and it invites automagic wiring nobody can trace back to a source.

**Alternative:** Register the provider explicitly in a `Group`. If the boilerplate is real, write a small helper that builds several `Factory` instances from a list of classes — that's application code, not a framework feature.

### In-package framework integrations

**What:** The core `modern-di` package ships no framework-specific code. Each integration (aiohttp, FastAPI, FastStream, Litestar, Starlette, Typer, Flask, gRPC, Celery, arq, taskiq, aiogram, pytest) is a separate `modern-di-*` package with its own release cadence.

**Why:** Bundling integrations into core would couple the library's release cadence to every framework's own churn, and would erode the zero-dependency guarantee that lets `modern-di` itself stay dependency-free. The separate-repo model is a standing architectural decision (see [`writing-integrations.md`](../integrations/writing-integrations.md)), not an oversight.

**Alternative:** Install the matching adapter package — see the [Quickstart](../index.md) for the current list — or write your own following [Writing an integration](../integrations/writing-integrations.md).

### Graph rendering / visualization tooling

**What:** modern-di has no built-in way to render the dependency graph as a picture — no ASCII art, no bundled renderer, no `plot()`/`render()` call, no image output.

**Why:** Rendering is a standalone subsystem (choosing, drawing, and maintaining a diagram toolchain) rather than an extension of an existing primitive, so it sits outside the conservative feature set and the zero-dependency guarantee. `validate()`'s aggregated, all-errors-at-once text report already surfaces the graph's problems without a new dependency or output format.

**Alternative:** None shipped today. If you need a picture of the graph, walk `Group.get_providers()` yourself and feed the edges to the diagram tool of your choice.

## See also

- [About DI](about-di.md) — the framework-agnostic introduction.
- [Migration from `that-depends`](../migration/from-that-depends.md) — what these decisions changed compared to the older framework.
