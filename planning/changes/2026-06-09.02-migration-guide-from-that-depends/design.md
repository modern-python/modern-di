---
status: shipped
date: 2026-06-09
slug: migration-guide-from-that-depends
summary: Migration guide from that-depends covering all provider types and conceptual shifts.
supersedes: null
superseded_by: null
pr: 198
outcome: docs/migration/from-that-depends.md published.
---

# Spec: Rewrite `from-that-depends.md` migration guide

**Date:** 2026-06-09
**Target file:** `docs/migration/from-that-depends.md`
**Goal:** A user migrating an existing `that-depends` codebase to `modern-di` can do so without surprises. Every provider type and core concept in `that-depends` has a documented mapping (or a documented "no equivalent" with workaround).

## Problem

The current guide covers only six of `that-depends`'s twelve+ providers, omits the biggest conceptual shifts (Group ≠ Container, sync-only resolution, async via lifespan), and contains internal inconsistencies (variable renames break the routes example). Migrators following it top-to-bottom will hit undefined symbols and unanswered questions.

## Scope decision

**Full restructure** (not targeted patches). The guide grows from ~210 lines to ~400–450 lines, organized so a migrator can `Ctrl-F` for the `that-depends` symbol they have in their code.

## Target structure

The new file follows this outline. Section numbers are stable; existing content is reused where it's correct.

### 1. Install

Keep the existing tabbed install snippet for `modern-di`. Add a second tabbed block listing the integration packages (`modern-di-fastapi`, `modern-di-litestar`, `modern-di-faststream`, `modern-di-typer`, `modern-di-pytest`) so users see them up front.

### 2. Key conceptual shifts (NEW)

Three short bullets explaining the mental model changes. This is the most important new section — most migrator confusion stems from these:

- **Group is a schema, Container is the runtime.** In `that-depends`, `BaseContainer` subclasses are both the schema and the runtime container — you resolve directly from the class. In `modern-di`, `Group` is a namespace-only class (you cannot instantiate it) and you create the runtime `Container(groups=[MyGroup])` separately, typically once at app start.
- **Resolution is sync-only.** `modern-di` removed async resolution. There is no `AsyncFactory`, `AsyncSingleton`, or `await container.resolve(...)`. Async resources are created in the framework's lifespan (see §6).
- **Scopes are explicit.** `Scope.APP → SESSION → REQUEST → ACTION → STEP`. A provider can only depend on providers of equal-or-broader scope (lower int). The framework integration creates the per-request child container automatically.

### 3. Provider mapping table (NEW)

A reference table — one row per `that-depends` provider — that drives the rest of the doc. Each row links to the section below that covers the migration.

| that-depends | modern-di replacement | Where to look |
|---|---|---|
| `Factory` | `providers.Factory(...)` | §4 |
| `Singleton` | `providers.Factory(..., cache_settings=CacheSettings())` | §4 |
| `Resource` (sync gen / ctx mgr) | `providers.Factory(..., cache_settings=CacheSettings(finalizer=...))` | §4 |
| `Resource` (async gen / ctx mgr) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | §6 |
| `ContextResource` | `providers.Factory(scope=Scope.REQUEST, ...)` | §5 |
| `AsyncFactory` | Lifespan-managed; expose via `ContextProvider` or sync wrapper | §6 |
| `AsyncSingleton` | Lifespan-managed; expose via `ContextProvider` | §6 |
| `Object` | `providers.Factory(creator=lambda: value, cache_settings=CacheSettings())` | §4 |
| `List` | `providers.Factory` with a creator returning a list | §4 |
| `Dict` | `providers.Factory` with a creator returning a dict | §4 |
| `Selector` | No direct equivalent; wrap selection in a `Factory` creator | §10 |
| `AttrGetter` (`provider.attr`) | No direct equivalent; access attribute inside creator | §10 |
| `ThreadLocalSingleton` | No direct equivalent; use `threading.local()` inside creator | §10 |
| `State` | `ContextProvider(context_type=T)` + `set_context(T, value)` | §5 |
| `Provider.bind(Type)` | `providers.Alias(source_type=Concrete, bound_type=Abstract)` | §4 |
| `@inject` + `Provide[T]()` (web) | `FromDI(T)` from framework integration | §9 |
| `@inject` + `Provide[T]()` (non-web) | Explicit `container.resolve(T)` at call sites | §10 |
| `container_context()` | `build_child_container(scope=..., context=...)` | §5 |
| `DIContextMiddleware` | `setup_di(app, container)` / `ModernDIPlugin(container)` | §8 |
| `fetch_context_item` / `_by_type` | `ContextProvider(context_type=T)` | §5 |
| `init_resources()` | Lazy initialization — no equivalent needed | §7 |
| `tear_down()` / `tear_down_sync()` | `await container.close_async()` / `container.close_sync()` | §7 |
| `override_providers_sync({...})` | `container.override(provider, mock)` | §7 |
| `provider.override_sync(mock)` | `container.override(provider, mock)` | §7 |

### 4. Migrate the dependency graph

Reuse the existing worked example but fix the bugs:

- **Bug A1:** Use one consistent name. Either `decks_service` / `DecksService` throughout, or `decks_repository` / `DecksRepository` throughout — and update the routes section to match.
- **Bug A2:** Add one sentence: *"In `modern-di`, when you put a provider inside `kwargs={...}`, it is detected and resolved automatically. There is no `.cast` indirection."*
- **Bug A4:** Add the `Container(groups=[Dependencies])` instantiation step explicitly to this section instead of deferring it to §8.

Then add per-provider mini-examples — one block each for the simple mappings: `Singleton`, sync `Resource`, `Object`, `List`/`Dict`, `Alias` (for `bind(Type)`). Keep them short; the table above is the index.

### 5. Context resources and request scope (NEW)

Replace the bare prose mention. Cover three cases with one short example each:

1. **`ContextResource` with framework integration.** The integration creates the REQUEST-scope child container per request; the user just writes `providers.Factory(scope=Scope.REQUEST, creator=..., cache_settings=CacheSettings(finalizer=...))`.
2. **Manual scope management (replaces `container_context()` outside web frameworks).** Use `with container.build_child_container(scope=Scope.REQUEST) as request_container: ...` — the context manager calls finalizers automatically.
3. **Injecting custom context (replaces `State`, `fetch_context_item`, `fetch_context_item_by_type`).** Declare `providers.ContextProvider(context_type=MyType)`, then `container.build_child_container(scope=..., context={MyType: instance})` or `child.set_context(MyType, instance)` before resolving.

### 6. Async resources (NEW — biggest gap)

The official pattern is **"async lives in the lifespan, not in the resolve path."** Cover three scenarios:

1. **Sync creator, async finalizer.** Most common case (e.g. SQLAlchemy `create_async_engine` returns synchronously; disposal is async). Use `CacheSettings(finalizer=async_close_fn)`. The framework integration calls `await container.close_async()` at shutdown, which detects and awaits async finalizers.
2. **Async creator (e.g. `await create_redis_pool()`).** Do the async work in the framework's lifespan/startup, then inject the resulting object as context. Show a FastAPI example:

   ```python
   @contextlib.asynccontextmanager
   async def lifespan(app: fastapi.FastAPI) -> AsyncIterator[None]:
       async with container:  # closes on exit
           redis = await create_redis_pool()
           container.set_context(Redis, redis)
           try:
               yield
           finally:
               await redis.close()
   ```

   Then reference it with `providers.ContextProvider(context_type=Redis, scope=Scope.APP)` and consume via `container.resolve(Redis)` or inject by type.

3. **`AsyncFactory` per-request work.** If the per-request resource genuinely requires `await` at construction time (e.g. acquiring a session from an async pool), wrap it so the *creator* is sync but returns an already-acquired object. Often the async work is in the *finalizer* (release the session), which is already supported. If the construction itself must be async, do it in the framework's per-request hook and inject via `set_context` on the child container.

Call out explicitly: **there is no plan to add async resolution back to `modern-di`.** Don't write code that expects it.

### 7. Lifecycle and testing

**Lifecycle.**

- `init_resources()`: no equivalent — `modern-di` is fully lazy. Anything that needs eager warmup happens in the framework's startup hook (or call `container.resolve(T)` for the things you want pre-built).
- `tear_down()` / `tear_down_sync()`: `await container.close_async()` / `container.close_sync()`. Both also work as (async) context managers — `async with container:` ensures cleanup. The framework integrations call this automatically at app shutdown.

**Testing.**

- `container.override_providers_sync({name: mock})` → `container.override(Dependencies.some_provider, mock)`. Note: keyed by **provider reference**, not name.
- `provider.override_sync(mock)` → same as above; no provider-level override API.
- `container.reset_override(provider)` to clear; `container.reset_override()` (no arg) to clear all.
- Point readers at `modern-di-pytest` (`modern_di_fixture`, `expose`) for fixture-based test wiring. The package is separately installed — `pip install modern-di-pytest`.

**Validation.**

- `Container(groups=[...], validate=True)` runs cycle/scope-chain checks at startup — recommend turning it on during migration as a safety net.

### 8. Framework integration

Keep existing FastAPI and LiteStar tabs. Add FastStream and Typer tabs (links to integration doc pages; full setup code lives in those docs). One sentence per framework about what the integration does (creates child containers per request/message/CLI invocation; calls `close_async()` at shutdown).

### 9. Routes

Keep existing FastAPI and LiteStar examples. Fix Bug A1 (variable/type name consistency with §4). Add a brief note that `FromDI(T)` replaces both `fastapi.Depends(Provide[T])` and `litestar.di.Provide`.

### 10. Things with no direct equivalent (NEW)

Short list — one paragraph each — covering:

- `Selector` → write a creator that picks based on whatever the selector depended on; or use `Alias` if the choice is static.
- `AttrGetter` (`provider.attr` syntax) → resolve the parent in the creator, return the attribute.
- `ThreadLocalSingleton` → call `threading.local()` inside a cached `Factory`'s creator.
- `@inject` for non-framework functions → call `container.resolve(T)` explicitly at the call site, or expose the function via a framework integration and use `FromDI`.

## Out of scope

- Changing any existing provider documentation pages outside `docs/migration/`.
- Adding new examples beyond the migration use case.
- Writing migration scripts or codemods.
- Updating `that-depends`'s own README pointer to this doc (already correct).

## Acceptance criteria

1. Every provider listed in `that_depends/providers/__init__.py`'s `__all__` has either a row in the §3 mapping table with a documented replacement, or a paragraph in §10 explaining the lack of a direct equivalent and a workaround.
2. The §4 worked example is internally consistent (no variable rename between Dependencies and routes).
3. A user with an async `that-depends` codebase finds enough guidance in §6 to migrate without raising an issue.
4. Provider override / testing migration is documented in §7 (not just deferred to `modern-di-pytest`).
5. The `Group` ≠ `Container` distinction is stated explicitly in §2.

## Self-review (post-write)

- Placeholder scan: no TBD/TODO; every section has at least one code block where the structure calls for one.
- Internal consistency: the §3 table's "where to look" column matches the actual section content.
- Scope: single-file rewrite; no codemods or upstream package changes implied.
- Ambiguity: the async section explicitly states "no plan to add async resolution back" — no reader can interpret §6 as a temporary workaround pending an async API.
