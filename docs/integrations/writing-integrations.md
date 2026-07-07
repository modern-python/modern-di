# Writing an integration

This page is the specification for building a **modern-di integration** for a
framework that does not yet have one (an ASGI app, a message broker, a CLI, a
test runner...). It is written to be followed step by step: implement the
contract below, mirror the scaffolding, and check every box in the final
checklist.

An integration does three jobs and nothing more:

1. **Own the root container's lifecycle** — open it when the app starts, close
   it when the app stops.
2. **Open a child container per unit of work** — a request, a message, a
   command — injecting the framework's connection object as context, and close
   it when that unit ends.
3. **Bridge modern-di into the framework's own injection** — so a handler can
   ask for a provider or a type and receive the resolved value.

Everything else is framework-specific plumbing to realize those three jobs.

## The contract

Every integration exposes the following. Types are shown for an async web
framework; swap `async`/`close_async` for `close_sync` in a synchronous one.

### 1. Connection `ContextProvider`(s)

One module-level provider per **connection kind** the framework has. Each pairs
the framework's connection type with the [scope](../providers/scopes.md) its
child container should open at. This is the single source of the
kind → scope mapping; `setup_di` registers them and the child-container builder
dispatches off them.

```python
from modern_di import Scope, providers

myfw_request_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=myfw.Request)
myfw_websocket_provider = providers.ContextProvider(scope=Scope.SESSION, context_type=myfw.WebSocket)

_CONNECTION_PROVIDERS = (myfw_request_provider, myfw_websocket_provider)
```

A framework with a single connection kind (a message, a CLI command) has one
provider — or, if the unit of work carries no injectable connection object
(Typer commands), none at all.

### 2. `setup_di(app, container) -> Container`

Attach the root container to the framework's application state, register the
connection providers, and wire the root container's lifecycle to app
startup/shutdown. Return the container.

```python
def setup_di(app: myfw.App, container: Container) -> Container:
    app.state.di_container = container            # attach
    container.add_providers(*_CONNECTION_PROVIDERS)  # register
    # wire lifecycle (see "Lifecycle rules" below)
    return container
```

Frameworks with a plugin system realize this differently: Litestar ships a
`ModernDIPlugin(InitPlugin)` whose `on_app_init` does the same three steps
instead of a free `setup_di` function. Prefer the framework's idiomatic
extension point.

### 3. `fetch_di_container(app_or_ctx) -> Container`

Read the root container back out of framework state. This is where the
child-container builder and any helpers get at the root.

```python
def fetch_di_container(app: myfw.App) -> Container:
    return typing.cast(Container, app.state.di_container)
```

Store and read under a **named constant**, not a repeated string literal, when
the framework uses a string-keyed store (FastStream's `ContextRepo`, Typer's
`ctx.obj`); it keeps writer and reader in provable agreement.

### 4. Per-unit-of-work child-container builder

Build a child container at the connection's scope, inject the connection object
as context, hand it to the handler, and **close it in `finally`**. The shape
depends on how the framework runs handlers:

- **Dependency generator** (FastAPI, Litestar) — an `async def` that `yield`s
  the container and closes after:

  ```python
  async def build_di_container(connection: HTTPConnection) -> typing.AsyncIterator[Container]:
      context: dict[type[typing.Any], typing.Any] = {}
      scope = None
      for provider in _CONNECTION_PROVIDERS:
          if isinstance(connection, provider.context_type):
              context[provider.context_type] = connection
              scope = provider.scope
              break
      container = fetch_di_container(connection.app).build_child_container(context=context, scope=scope)
      try:
          yield container
      finally:
          await container.close_async()
  ```

- **Middleware** (FastStream) — a `BaseMiddleware` whose `consume_scope` builds
  the child, stashes it in the framework context for the duration of the call,
  and closes it in `finally`.

- **Decorator** (Typer) — an `inject` decorator that wraps the command, opens a
  child container for the command's duration, resolves the marked parameters,
  and closes the container (synchronously) on exit.

### 5. `FromDI` marker + `Dependency` resolver

`FromDI(dependency)` accepts a provider **or** a type and, at a handler's call
site, stands in for the resolved value: `x: Annotated[Foo, FromDI(foo_provider)]`.
How it delivers that value splits into two modes depending on the framework:

- **Native-DI frameworks** (FastAPI, FastStream, Litestar) have a per-handler
  injection seam — `Depends`, `Provide`. `FromDI` returns that native marker and
  the framework calls your resolver with the request container. This is the path
  documented below.
- **Frameworks with no request-scoped DI** (Typer/Click CLIs, argparse, task
  runners) have no seam. `FromDI` returns an inert marker and a **decorator**
  does the resolution. See [Frameworks without native
  DI](#frameworks-without-native-di-the-decorator-path).

For the native-DI path, `FromDI` returns the framework's injection marker
wrapping a frozen, slotted dataclass whose `__call__` receives the request
container (via the framework's own DI) and dispatches on the argument kind.

```python
@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(self, request_container: typing.Annotated[Container, myfw.Depends(build_di_container)]) -> T_co:
        return request_container.resolve_dependency(self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> T_co:  # noqa: N802
    return typing.cast(T_co, myfw.Depends(Dependency(dependency)))
```

The dispatch is a single call, invariant across every integration and both
modes: `resolve_dependency` takes either an `AbstractProvider` or a bare type
and routes to `resolve_provider`/`resolve` accordingly — overrides, caching,
and did-you-mean suggestions are inherited from whichever it dispatches to.
`FromDI` is spelled in PascalCase (with `# noqa: N802`) because it stands in for
a type at call sites.

## Lifecycle rules

- **Reopen the root container on startup.** A container that was closed on
  shutdown emits a `ContainerClosedWarning` (and, in 3.0, raises
  `ContainerClosedError`) if reused without reopening. Reopening on each
  startup lets a second lifespan cycle (test client re-entry, broker restart)
  work.
    - With a context-manager lifespan: `async with fetch_di_container(app): yield`
      — `__aenter__` reopens, `__aexit__` closes. Compose *around* any existing
      lifespan rather than replacing it.
    - With callback hooks: `app.on_startup(container.open)` and
      `app.after_shutdown(container.close_async)`. Reopening an already-open
      container is a no-op.
- **Always close the child container in `finally`.** Never leak a unit-of-work
  container on the error path.
- **Match async vs sync to the framework.** Async frameworks use
  `close_async`; a synchronous CLI uses `close_sync`.

## Scope mapping

Map each connection kind to the scope its child container opens at. Follow the
[scope hierarchy](../providers/scopes.md#the-scope-dependency-rule):

| Unit of work | Scope | Rationale |
|---|---|---|
| HTTP request | `REQUEST` | one child per request |
| WebSocket connection | `SESSION` | outlives individual messages on the socket |
| Broker message | `REQUEST` | one child per consumed message |
| CLI command | `REQUEST` | one child per command invocation |
| Nested action within a unit | `ACTION` (a further child) | opt-in deeper scope, e.g. a Typer `action_scope` |

## How the existing integrations realize the contract

Pattern-match your framework to the closest precedent.

| Contract point | FastAPI | FastStream | Litestar | Typer |
|---|---|---|---|---|
| Root attach + lifecycle | `setup_di` + composed lifespan | `setup_di` + `on_startup`/`after_shutdown` callbacks | `ModernDIPlugin.on_app_init` + lifespan | `setup_di` via `ctx.obj` |
| Fetch root | `app.state.di_container` | `context.get("di_container")` | `app.state.di_container` | `ctx.obj["di_container"]` |
| Connection providers | request + websocket | message | request + websocket | none (command has no connection object) |
| Child builder | `async` dependency generator | `BaseMiddleware.consume_scope` | `async` dependency generator | `inject` decorator |
| `FromDI` bridge | `fastapi.Depends(Dependency(...))` | `faststream.Depends(Dependency(...))` | `Provide(_Dependency(...))` | inert `_FromDI` marker + `inject` |
| Child close | `close_async` | `close_async` | `close_async` | `close_sync` |

The **Starlette** integration ([`modern-di-starlette`](starlette.md)) is the
reference for a **middleware + decorator hybrid**: Starlette has no native DI,
so a pure-ASGI middleware owns the child-container lifecycle (like FastStream)
while an `@inject` decorator with an inert `FromDI` marker does resolution (like
Typer). It splits the two responsibilities of the decorator path — the middleware
builds and closes the per-connection child, the decorator only reads it back from
the ASGI scope and resolves. See [Frameworks without native
DI](#frameworks-without-native-di-the-decorator-path).

The **aiohttp** integration ([`modern-di-aiohttp`](aiohttp.md)) is another
middleware + decorator hybrid, for a non-ASGI server where the only connection
object at middleware entry is `web.Request` — a WebSocket is an upgraded HTTP
request, not a distinct type. It detects a WebSocket via
`web.WebSocketResponse().can_prepare(request).ok`, opens a `Scope.REQUEST`
child for an HTTP request or a `Scope.SESSION` child for a WebSocket, and —
because both connection providers bind `web.Request` — registers
`aiohttp_request_provider` by type while keeping `aiohttp_websocket_provider`
reference-only (`bound_type=None`). Its root lifecycle rides aiohttp's
`on_startup`/`on_cleanup` signals rather than a composed lifespan.

The **pytest** integration
([`modern-di-pytest`](pytest.md)) is a different shape: it has no app to wire, so
instead of `setup_di`/`FromDI` it exposes `modern_di_fixture` (turn one
dependency into a fixture) and `expose` (turn a `Group`'s providers into
fixtures). It resolves from a user-supplied `di_container` fixture. Follow it
when integrating a **test runner** rather than an application framework.

## Frameworks without native DI (the decorator path)

Contract points 4 and 5 assume a **per-handler injection seam** — FastAPI /
FastStream `Depends`, Litestar `Provide` — that you hand a native marker and
that calls your resolver with the request container. Some frameworks have none:
a Typer/Click command, an argparse handler, or a plain task callable receives
only what the framework's argument parser binds. There is nowhere to inject.

For these, `FromDI` becomes an inert annotation marker and a **decorator** does
the work native DI would have. [`modern-di-typer`](typer.md)'s `@inject` is the
reference implementation — reach for this shape whenever the framework runs
handlers as plain callables it parses arguments for. The decorator can build the
per-call child container itself (Typer), or read one built by middleware
([`modern-di-starlette`](starlette.md) builds it in a pure-ASGI middleware and the
decorator only resolves from it) — the resolution mechanics below are the same
either way.

### How it works

- **`FromDI` is inert.** It returns a frozen `_FromDI(provider)` dataclass, cast
  to the resolved type so checkers still see `T`. On its own it does nothing; the
  decorator interprets it.

  ```python
  service: typing.Annotated[MyService, FromDI(Dependencies.service)]
  ```

- **Decoration time** — the decorator introspects
  `typing.get_type_hints(func, include_extras=True)`, finds parameters whose
  `Annotated` metadata holds a `_FromDI`, then **rewrites the signature**:
  *remove* those parameters (so the arg parser never treats them as CLI options)
  and *insert* the framework's context parameter (`typer.Context`) at position 0
  if the handler didn't declare one. Assign the cleaned signature to
  `wrapper.__signature__` — the parser reads that, and `functools.wraps` alone
  won't set it.

- **Call time** — bind incoming args against the rewritten signature, pull out
  the context object (deleting it again if the decorator added it implicitly),
  build the per-call child container, resolve each marked parameter by kind
  (contract point 5), fill them into the call by name, invoke the original
  function, and `close_sync` the container in `finally`.

DI parameters coexist with ordinary framework parameters because the decorator
strips **only** the marked ones; everything else still reaches the parser.

### What changes vs. the native path

| Contract point | Native DI | Decorator |
|---|---|---|
| `FromDI` returns | framework marker (`Depends` / `Provide`) | inert `_FromDI` marker |
| Child container built by | framework, via your resolver | the decorator wrapper |
| Handler receives value via | framework's DI | signature rewrite + fill-by-name at call time |
| Root-container access | connection object passed in | framework's per-call context, injected into the signature if absent |
| Connection `ContextProvider` | one per connection kind | none — the handler carries no connection object |

### Pitfalls to get right

- **Set `wrapper.__signature__`.** Without it the parser still sees the stripped
  DI params and errors. (`__signature__` isn't in the stub, so
  `# ty: ignore[unresolved-attribute]`.)
- **Strip only DI params.** Leave real arguments/options in the signature or the
  framework stops parsing them.
- **Decorator order.** The framework's own registration decorator goes
  **outside** — `@app.command()` above `@inject` — so it registers the rewritten
  signature.
- **Isolate per-call state.** Stash the per-call container on a per-invocation
  store (`ctx.meta`), not shared app state (`ctx.obj`), so nested scopes can
  parent onto it and nothing leaks between invocations.
- **Keep nested scopes caller-driven.** Expose a helper (`action_scope(ctx)`)
  that yields a fresh deeper-scope child of the per-call container per `with`
  block, rather than auto-injecting one.

## Repo scaffolding

Each official integration is its own repository and PyPI package, mirroring the
`modern-di` repo's tooling.

- **Names.** Repo and PyPI package `modern-di-<framework>`; import package
  `modern_di_<framework>`.
- **Layout.**
    - `modern_di_<framework>/main.py` — the entire implementation.
    - `modern_di_<framework>/__init__.py` — re-export the public API from
      `main` and list it in an explicit `__all__` (this is the integration's
      surface; keep private helpers out of it).
- **`pyproject.toml`.** `name = "modern-di-<framework>"`,
  `description = "modern-di integration for <Framework>"`, dependencies
  `["<framework>>=...,<...", "modern-di>=<current>,<3"]`, the standard
  `classifiers` (Typed, supported Python versions) and `[project.urls]` pointing
  at the shared docs site and the integration's own repo. `version = "0"` — the
  release tag sets it.
- **Tests** (`tests/`):
    - `conftest.py` — fixtures that build an app, call `setup_di` (or install the
      plugin) with a `Container(groups=[Dependencies])`, and yield a test client.
    - `dependencies.py` — a sample `Group` with `Factory` providers at several
      scopes, plus providers that read the connection object (e.g. a request
      header) to prove context injection works.
    - `test_lifespan.py` (startup/shutdown + restart), `test_routes.py` /
      `test_commands.py` (resolution through `FromDI`), and `test_websockets.py`
      where the framework has websockets. Aim for the same 100%-coverage gate
      `modern-di` holds.
- **Mirror `modern-di`'s** `CLAUDE.md`, `Justfile`, and `architecture/` truth
  home. Keep resolution sync-only and add no runtime dependency beyond the
  framework and `modern-di`.
- **Docs.** Add a `docs/integrations/<framework>.md` usage page **in the
  `modern-di` repo** and a nav entry for it in `mkdocs.yml`; integrations do not
  ship their own docs site.
- **Release.** Tag-driven, mirroring `modern-di`: write release notes and push a
  bare semver tag off green `main`.

!!! tip "Planning convention"
    For the planning/change-management setup, following the
    [planning-convention](https://github.com/lesnik512/planning-convention) is
    recommended — the same two-axis convention the `modern-di` repo uses.

## Checklist

- [ ] Repo `modern-di-<framework>`, package `modern_di_<framework>`, `main.py` +
      re-exporting `__init__.py` with explicit `__all__`.
- [ ] One connection `ContextProvider` per connection kind, grouped in a single
      `_CONNECTION_PROVIDERS` tuple mapping kind → scope.
- [ ] `setup_di` (or a plugin) attaches the root container, registers the
      connection providers, and wires startup/shutdown.
- [ ] `fetch_di_container` reads the root container back out of framework state.
- [ ] A per-unit-of-work builder opens a child container at the right scope,
      injects the connection as context, and closes it in `finally`.
- [ ] Root container **reopens on startup** so restarts don't emit a
      `ContainerClosedWarning` (or, in 3.0, raise `ContainerClosedError`).
- [ ] `close_async` / `close_sync` matches the framework's async-ness.
- [ ] `FromDI` accepts `AbstractProvider[T] | type[T]` and resolves it via
      `resolve_dependency`.
- [ ] **No native DI?** `FromDI` is an inert marker and a decorator rewrites the
      handler signature (strips DI params, threads the context object, sets
      `wrapper.__signature__`), resolves at call time, and closes the per-call
      container in `finally`. See the [decorator
      path](#frameworks-without-native-di-the-decorator-path).
- [ ] Tests cover lifespan (incl. restart), resolution through `FromDI`, and
      context injection from the connection object; coverage gate green.
- [ ] Usage page + `mkdocs.yml` nav entry added in the `modern-di` repo.
- [ ] `CLAUDE.md`, `Justfile`, `architecture/` mirrored;
      [planning-convention](https://github.com/lesnik512/planning-convention)
      followed.
