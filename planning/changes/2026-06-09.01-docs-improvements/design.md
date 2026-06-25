---
status: shipped
date: 2026-06-09
slug: docs-improvements
summary: Docs-site improvements: recipes section, concept pages, refreshed Quick Start.
supersedes: null
superseded_by: null
pr: 198
outcome: Docs-site improvements shipped.
---

# Spec: Docs improvements — recipes + concept pages

**Date:** 2026-06-09
**Goal:** A reader new to `modern-di` can go from install to a realistic wired app, and a reader who already uses it can find canonical solutions for SQLAlchemy, async startup, multi-group organization, and testing in one place. Concretely: add a Recipes section drawn from real services, consolidate the two most-scattered concepts (scopes, lifecycle) into dedicated pages, and refresh the Quick Start example.

## Scope

**Option B** from the brainstorming round:

- Add **5 recipes** under a new top-level Recipes section.
- Add **2 new concept pages** (`providers/scopes.md`, `providers/lifecycle.md`) consolidating content currently split across `about-di.md`, `factories.md`, and `container.md`.
- Refresh the **Quick Start** with a realistic example.
- Update **mkdocs.yml** nav.

Out of scope: renaming `Providers` → `Concepts`, merging `integrations/pytest.md` into `testing/`, rewriting thin pages (`resolving.md`, `dev/decisions.md`). Those are Option C — defer.

## Deliverables

### Part 1 — Recipes section (5 pages)

Each recipe follows the `httpware` recipe template observed in `/Users/kevinsmith/src/pypi/httpware/docs/recipes/`:

1. One-sentence problem statement at the top.
2. Minimal working solution with code.
3. Pitfalls / variations callout.
4. "See also" links to related docs and integrations.
5. Reader assumed to already know the basics (Quick Start + provider concepts).

Target length: 150–400 words of prose + a complete code example per recipe. Recipes are copy-pasteable starting points, not tutorials.

#### Recipe 1: `recipes/sqlalchemy.md` — Async SQLAlchemy engine, session, repository

Source: `litestar-sqlalchemy-template` (canonical pattern), cross-checked against `chats`.

- **Problem:** Wire `create_async_engine` + `AsyncSession` + repository classes through `modern-di` so the engine is shared, sessions are per-request, and cleanup happens automatically.
- **Solution:** APP-scoped `Factory` for the engine with async finalizer `engine.dispose()`; REQUEST-scoped `Factory` for the session with `kwargs={"engine": engine_provider}` and async finalizer `session.close()`; REQUEST-scoped `Factory` for each repository with `kwargs={"session": session_provider}`.
- **Caveats:** `CacheSettings.finalizer` auto-detects async functions — no flag needed. If you wrap test connections, override the session's `close()` to handle the non-engine case (the template does this with a `CustomAsyncSession` — link to it, don't reproduce).
- **See also:** `providers/lifecycle.md`, `integrations/litestar.md`, `integrations/fastapi.md`, `recipes/testing-overrides.md`.

#### Recipe 2: `recipes/async-lifespan.md` — Async resources initialized in a lifespan

Source: `chats` (Redis, Kafka) + the async-via-lifespan pattern documented in the migration guide §6.

- **Problem:** A resource needs `await` to construct (Redis pool, Kafka producer, async HTTP client with auth handshake). `modern-di` resolution is sync, so the construction has to live somewhere else.
- **Solution:** Construct the resource in the framework's lifespan; call `container.set_context(MyType, instance)` to register it; declare `providers.ContextProvider(scope=Scope.APP, context_type=MyType)` so downstream factories can depend on the type.
- **Caveats:** Use `async with container:` inside the lifespan to ensure `close_async()` runs on exit. Set context **before** yielding; setting it on a parent after children exist does not propagate. Choose APP scope unless the resource is per-session.
- **See also:** `providers/lifecycle.md`, `providers/context.md`, `migration/from-that-depends.md#6-async-resources`.

#### Recipe 3: `recipes/multi-group.md` — Organize a large container with multiple Groups

Source: `chats` (Database / Redis / Outbox / Kafka / Workers / UseCases).

- **Problem:** Service has 30+ providers and stuffing them in one Group is unreadable.
- **Solution:** Split providers into multiple `Group` subclasses by domain. Pass them all to `Container(groups=[DatabaseGroup, RedisGroup, UseCases])`. Cross-group dependencies wire by type — no explicit references needed.
- **Caveats:** Two groups defining attributes with the same name raise `ValueError` at container creation. Mention `litestar`'s `autowired_groups` — it can register every provider in named groups as Litestar dependencies automatically.
- **See also:** `providers/factories.md`, `integrations/litestar.md` (autowired_groups), `providers/scopes.md`.

#### Recipe 4: `recipes/testing-overrides.md` — Transactional test fixture with `container.override`

Source: `litestar-sqlalchemy-template`'s `db_session` fixture + `chats` test patterns.

- **Problem:** Tests need a real database session that rolls back after each test, without touching production wiring.
- **Solution:** In a `pytest` fixture, open a connection inside a nested transaction and `container.override(Dependencies.engine, connection)` so providers that ask for the engine receive the test connection. Yield; then `container.reset_override(Dependencies.engine)` and roll back. Show both the `modern-di-pytest` and the manual-override variants.
- **Caveats:** Overrides are keyed by provider reference (not name). Overrides are shared across the container tree — fine for tests, watch for it in production. For repositories that take a session, override the session, not the engine, unless you want SQLAlchemy to redo binding.
- **See also:** `testing/fixtures.md`, `integrations/pytest.md`, `recipes/sqlalchemy.md`.

#### Recipe 5: `recipes/request-scoped-engine.md` — Request-scoped engine selection (read replicas)

Source: `chats`.

- **Problem:** Route `GET` requests to a read-replica engine, mutating requests to the primary, without changing handler code.
- **Solution:** Two APP-scoped engine factories (primary + replica). A REQUEST-scoped factory that consumes the `Request` (via the framework integration's request `ContextProvider`) and returns the appropriate engine. Repositories depend on the *request-scoped* engine.
- **Caveats:** Marked as advanced. Requires understanding that ContextProvider for the request is automatically registered by the framework integration. Don't try to attach the choice to a session-level pool that holds long connections — the REQUEST-scope factory picks per request, not per pool.
- **See also:** `recipes/sqlalchemy.md`, `providers/context.md`, `providers/scopes.md`.

### Part 2 — New concept pages (2 pages)

#### `providers/scopes.md`

Consolidates content currently split across `container.md`, `factories.md`, and `about-di.md`.

Sections:

1. **The scope chain.** `APP → SESSION → REQUEST → ACTION → STEP`. One-line description of what each is for; concrete framework examples (APP = app start; SESSION = websocket; REQUEST = HTTP request; ACTION = sub-step inside a request; STEP = sub-step inside ACTION).
2. **The container tree.** Root is APP; children are built from parents via `build_child_container(scope=...)`. Children inherit providers and overrides registries; have their own cache and context registries.
3. **Scope dependency rule.** A provider can only depend on providers at the same or broader (lower int) scope. Why: lifetime safety — a request-scoped session should not be captured by an app-scoped singleton.
4. **Building child containers.** Manual (`with container.build_child_container(scope=Scope.REQUEST) as request_container:`) vs. framework-managed (integration creates the child container automatically per request).
5. **Resolving across scopes.** Resolution walks up to the container at the provider's declared scope.

After this page lands, trim the duplicate scope content out of `factories.md` and `container.md` and link to this page.

#### `providers/lifecycle.md`

Consolidates content currently scattered through `factories.md`, `container.md`, and the migration guide.

Sections:

1. **Lazy initialization.** Providers are created on first resolve. There is no `init_resources()`. To pre-warm, call `container.resolve(SomeType)` explicitly at startup.
2. **Finalizers via `CacheSettings`.** `CacheSettings(finalizer=fn)` where `fn` can be sync or async — auto-detected. Finalizer receives the cached instance.
3. **`close_sync()` / `close_async()`.** What they do (run finalizers in reverse, clear cache). Context manager usage: `with container:` and `async with container:`.
4. **Per-scope finalization.** Child containers run their own finalizers on exit. Framework integrations close the per-request child container automatically at the end of the request.
5. **Validation.** `Container(groups=[...], validate=True)` runs cycle/scope checks at startup. Recommended.

After this page lands, link to it from `factories.md` (`cache_settings` section) and the migration guide.

### Part 3 — Quick Start refresh

The current `index.md` example uses `create_singleton() -> "some string"` and a `SimpleFactory` with dummy `dep1/dep2`. Replace with a small but realistic example: a `Settings` dataclass + a `Logger`-style service + a request-scoped `UserRepository` so the reader sees APP and REQUEST scopes on real-looking types. Keep total length about the same.

Also update the "Use without integrations" section to use `async with` and demonstrate `close_async()` — most real users hit async resources first.

### Part 4 — mkdocs.yml nav changes

Add `Recipes` as a top-level section between Integrations and Testing:

```yaml
- Recipes:
    - Async SQLAlchemy: recipes/sqlalchemy.md
    - Async resources via lifespan: recipes/async-lifespan.md
    - Multi-Group organization: recipes/multi-group.md
    - Testing with overrides: recipes/testing-overrides.md
    - Request-scoped engine selection: recipes/request-scoped-engine.md
```

Add `Scopes` and `Lifecycle` to the Providers section (at the top, before existing pages):

```yaml
- Providers:
    - Scopes: providers/scopes.md
    - Lifecycle: providers/lifecycle.md
    - Factories: providers/factories.md
    - Context: providers/context.md
    - Container: providers/container.md
    - Alias: providers/alias.md
```

## Acceptance criteria

1. All 5 recipes ship with a complete, copy-pasteable code example that compiles against the current `modern-di` API (no pseudo-code).
2. `providers/scopes.md` is the single source of truth for the scope chain mental model; `factories.md` and `container.md` defer to it.
3. `providers/lifecycle.md` is the single source of truth for finalizers, `close_*`, and validation; other pages defer to it.
4. Quick Start uses non-toy types and shows async cleanup.
5. `mkdocs.yml` nav reflects all new pages.
6. Existing pages that previously held the consolidated content have their now-duplicate sections trimmed (factories.md, container.md, about-di.md).

## Implementation order

1. Concept pages first (`scopes.md`, `lifecycle.md`) — recipes link into them.
2. Recipes next (in the order listed above — SQLAlchemy first because the others reference it).
3. Quick Start refresh.
4. Nav update.
5. Trim duplicated sections from existing pages.

Each step is a separate commit; the whole thing is one PR.

## Self-review

- Placeholder scan: none.
- Internal consistency: recipes use the patterns described in their cited sources; concept pages own content that recipes link to.
- Scope: 5 recipes + 2 concept pages + Quick Start refresh + nav + trim duplicates. Fits one PR; one implementation plan.
- Ambiguity: Recipe 4 says "Show both the modern-di-pytest and the manual-override variants" — keep both short (one short block each); recipe 5 is explicitly tagged advanced so readers know it's not the default pattern.
