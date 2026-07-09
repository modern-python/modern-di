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
Already shipped: aiohttp, FastAPI, Litestar, FastStream, Starlette, taskiq,
Typer (plus the `modern-di-pytest` plugin). The gap below is drawn from
Dishka's integration set and sorted by community demand — exploratory, not a
queue.

**Next up — highest demand, clear fit:**
- **Celery** — the largest task-queue install base in Python.
- **aiogram** — dominant async Telegram-bot framework; a new entrypoint class.

**Second wave — high value:**
- **Flask** — enormous WSGI install base; its sync model fits sync resolution.
- **arq** — async Redis task/job queue, common in FastAPI stacks.
- **gRPC** (`grpcio`) — steady enterprise demand; a new RPC entrypoint.

**Lower / niche demand:**
- **aiogram-dialog** — aiogram addon; only after aiogram lands.
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
- **Public, reproducible benchmark suite** with neutral methodology.
- **Optional OpenTelemetry instrumentation** of resolution and finalization.

### Docs & ecosystem
- More recipes and example apps; comparison and migration guides.

## Explicitly not planned

- **Async resolution** (`await container.resolve(...)`, `AsyncFactory`) — this is
  a deliberate design choice. Async setup/teardown happens in the framework
  lifespan; resolution stays synchronous.

## Feedback & contributions

Items here are open for discussion and contribution. Comment in
[Ideas Discussions](https://github.com/modern-python/modern-di/discussions) to
shape priorities or volunteer to build one.
