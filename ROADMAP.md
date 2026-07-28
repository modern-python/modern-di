# Roadmap

This roadmap is **exploratory** — a signal of direction and an invitation for
feedback, not a commitment to features or dates. If you have an opinion on any
item, or want to build one, please open or comment in
[Ideas Discussions](https://github.com/modern-python/modern-di/discussions).

## Guiding principles

- **Small, fully-typed, zero-dependency core.**
- **Sync resolution by design** — async work belongs in the framework lifespan,
  not in dependency resolution.
- **One typed wiring across every entrypoint** — FastAPI, Litestar, FastStream,
  Typer, plus workers and CLIs.
- **Official, uniformly-maintained integrations** over breadth at any cost.

## Under consideration

### More official integrations — "one wiring, every entrypoint"
Each new entrypoint lets your existing container cover more of your stack.
Already shipped: aiogram, aiohttp, arq, Celery, FastAPI, FastStream, Flask,
gRPC, Litestar, Starlette, taskiq, Typer (plus the `modern-di-pytest` plugin).
aiogram-dialog getters and callbacks are supported via the
`modern_di_aiogram.dialog` submodule. The gap below is drawn from Dishka's
integration set and sorted by community demand — exploratory, not a queue.

**Lower / niche demand:**
- **Sanic** — async web is already covered by FastAPI/Litestar/Starlette.
- **pyTelegramBotAPI** (`telebot`) — older sync Telegram library.

*Not planned:* **Click** — Typer already covers the CLI entrypoint and is
built on Click, so a separate adapter would be redundant.

*Community-maintained if contributed* (as Dishka treats them): Pyramid,
Strawberry, Quart, RQ, APScheduler, Jobify, Flet, ag2.

### Developer experience
- **Deeper pytest plugin** — parametrized overrides, autouse scope helpers,
  async-fixture ergonomics. (modern-di already ships a first-party pytest
  plugin; this makes it richer.)
- **First-class config providers** — pydantic-settings / environment / TOML.
- **Smoother abstract / `Protocol` → implementation binding** with clearer
  scope- and cycle-violation diagnostics.
- **Dependency-graph export** (Mermaid / Graphviz) for debugging and docs.

### Trust & observability
- **Public, reproducible benchmark suite** with neutral methodology —
  shipped; see [Performance](https://modern-di.modern-python.org/introduction/performance/).
- **Optional OpenTelemetry instrumentation** of resolution and finalization.
- **Trim the warm-singleton path (C2)** — the published scenario where modern-di
  trails by the widest margin, now 2.94x dependency-injector and 2.13x
  that-depends. Two Python method calls that were pure indirection on a warm hit
  — `ProvidersRegistry.resolver_for` on every top-level resolve and
  `CacheRegistry.fetch_cache_item` inside the compiled resolver — are inlined on
  their dict-lookup hit paths, with the method called only on a miss, keeping the
  cycle-safe compilation thunk and the shared-item guarantee intact;
  **shipped in 3.1.2**. The guard tier measured a ~25% faster warm hit
  (170 → 128 ns), and the published cell moved from 3.88x to 2.94x against
  dependency-injector and 2.80x to 2.13x against that-depends, with both rivals'
  absolutes unchanged — the check that the movement is modern-di's and not
  measurement drift. The bound stated when this was planned held: it trimmed the
  cell, it did not close it. dependency-injector's ~48 ns is a C-level slot read
  on a Cython core, which pure Python does not reach.
  A third step remains open and is **deliberately deferred**: an APP-scoped
  resolver could close over its `CacheItem` and reach ~16 ns, but the target is
  only invariant because one registry belongs to one root, so the registry would
  have to reference its root — the container reference cycle removed in 3.1.1.
  That needs a weakref and a proof, for ~30 ns.

### Docs & ecosystem
- **Canonical on-ramp per integration** — every official integration ships a
  runnable `examples/` app plus a normalized README `Usage example:` link, so a
  newcomer can adopt it in one sitting; **shipped**.
- More recipes; comparison and migration guides.

## Explicitly not planned

- **Async resolution** (`await container.resolve(...)`, `AsyncFactory`) — this is
  a deliberate design choice. Async setup/teardown happens in the framework
  lifespan; resolution stays synchronous.

## Feedback & contributions

Items here are open for discussion and contribution. Comment in
[Ideas Discussions](https://github.com/modern-python/modern-di/discussions) to
shape priorities or volunteer to build one.
