# Writing an integration

This page specifies how to build a modern-di integration for a framework that does not have one yet:
an ASGI app, a message broker, a CLI, a test runner. Implement the contract, mirror the scaffolding,
and work through the checklist at the end.

An integration does three jobs:

1. Own the root container's lifecycle: open it when the app starts, close it when the app stops.
2. Open a child container per unit of work (a request, a message, a command), injecting the
   framework's connection object as context, and close it when that unit ends.
3. Bridge modern-di into the framework's own injection, so a handler can ask for a provider or a type
   and receive the resolved value.

## The contract

Every integration exposes the following. The examples are for an async web framework; a synchronous
one swaps `async with` for `with` and `close_async` for `close_sync`.

### 1. Connection `ContextProvider`(s)

One module-level provider per connection kind the framework has. Each pairs the framework's connection
type with the [scope](../providers/scopes.md) its child container opens at, which makes these providers
the single source of the kind-to-scope mapping. `setup_di` registers them and the child builder
dispatches on them.

<!-- invisible-code-block: python
import contextlib
import dataclasses
import types
import typing

from modern_di import Container, Group, Scope, providers


@contextlib.asynccontextmanager
async def _no_lifespan(app: "_App") -> typing.AsyncIterator[None]:
    yield


class _App:
    def __init__(self) -> None:
        self.state = types.SimpleNamespace()
        self.lifespan = _no_lifespan


class _Request:
    def __init__(self, app: _App) -> None:
        self.app = app
        self.scope: dict[str, typing.Any] = {}


class _WebSocket:
    def __init__(self, app: _App) -> None:
        self.app = app
        self.scope: dict[str, typing.Any] = {}


myfw = types.SimpleNamespace(App=_App, Request=_Request, WebSocket=_WebSocket, Depends=lambda dependency: dependency)
HTTPConnection = _Request
T_co = typing.TypeVar("T_co", covariant=True)


class MyService: ...


class Dependencies(Group):
    service = providers.Factory(MyService, scope=Scope.REQUEST)
-->

```python
from modern_di import Scope, providers

myfw_request_provider = providers.ContextProvider(myfw.Request, scope=Scope.REQUEST)
myfw_websocket_provider = providers.ContextProvider(myfw.WebSocket, scope=Scope.SESSION)

_CONNECTION_PROVIDERS = (myfw_request_provider, myfw_websocket_provider)
```

With one connection kind (a broker message, a gRPC call) there is one provider, and FastStream and
FastMCP register it directly without a tuple. A unit of work with no injectable connection object, such
as a Typer command or a Celery task, has none.

### 2. `setup_di(app, container) -> Container`

Attach the root container to the application state, register the connection providers, wire the root
container's lifecycle to app startup and shutdown, and return the container:

```python
def setup_di(app: myfw.App, container: Container) -> Container:
    app.state.di_container = container
    container.add_providers(*_CONNECTION_PROVIDERS)
    original_lifespan = app.lifespan

    @contextlib.asynccontextmanager
    async def lifespan(app_: myfw.App) -> typing.AsyncIterator[None]:
        async with original_lifespan(app_), fetch_di_container(app_):
            yield

    app.lifespan = lifespan
    return container
```

A framework with a plugin system gets the same three steps through its own extension point. Litestar's
`ModernDIPlugin(InitPlugin)` does them in `on_app_init` instead of a free `setup_di` function.

`add_providers` is a startup-time operation and is not coordinated with concurrent resolves, so call it
from `setup_di`, never from request-handling code.

### 3. `fetch_di_container(app_or_ctx) -> Container`

Read the root container back out of framework state. The child builder and any helpers get at the root
through it. When the lookup fails, raise a `RuntimeError` that names the missing call, with `from None`
so the framework's `AttributeError` or `KeyError` on a private key does not trail it:

```python
def fetch_di_container(app: myfw.App) -> Container:
    try:
        return typing.cast(Container, app.state.di_container)
    except AttributeError:
        msg = (
            "No modern-di container found on the app. "
            "Call setup_di(app, container) before using FromDI or fetch_di_container."
        )
        raise RuntimeError(msg) from None
```

The same rule covers every place an integration looks a container up, including the per-call child
that a decorator reads. Use a plain `RuntimeError` rather than a `ModernDIError` subclass, because the
fault is in the framework wiring and `modern_di.integrations` defines no exceptions. Pin the message
with a test. FastMCP is the one variation: it raises a subclass of both `RuntimeError` and
`FastMCPError`, so the client sees the message.

When the framework has a string-keyed store (FastStream's `ContextRepo`, Typer's
`context_settings["obj"]`), keep the key in a named constant that both the writer and the reader use.

<!-- invisible-code-block: python
app = myfw.App()
setup_di(app, Container(groups=[Dependencies]))
for _ in range(2):
    async with app.lifespan(app):
        assert not fetch_di_container(app).closed
    assert fetch_di_container(app).closed
-->

<!-- raises: RuntimeError -->
```python
fetch_di_container(myfw.App())
```

### 4. Per-unit-of-work child-container builder

Build a child container at the connection's scope, inject the connection object as context, hand the
child to the handler, and close it when the unit of work ends. `async with` on the child closes it on
every exit path. Who builds the child depends on how the framework runs handlers:

- A dependency generator (FastAPI, Litestar, taskiq) yields the child. With several connection kinds,
  `modern_di.integrations.classify_connection` picks the first provider the connection is an instance
  of and returns its scope and a `{context_type: connection}` context, or `None` when nothing matches:

  ```python
  from modern_di import integrations

  async def build_di_container(connection: HTTPConnection) -> typing.AsyncIterator[Container]:
      match = integrations.classify_connection(connection, _CONNECTION_PROVIDERS)
      async with fetch_di_container(connection.app).build_child_container(
          scope=match.scope if match else None,
          context=match.context if match else None,
      ) as container:
          yield container
  ```

  With one connection kind, `integrations.bind(provider, connection)` returns the same scope and
  context without the `isinstance` scan.

- Middleware or a framework hook builds the child, stores it where the handler's code can find it for
  the duration of the call, and closes it afterwards. FastStream does this in
  `BaseMiddleware.consume_scope`, Starlette in a pure-ASGI middleware, Flask in `before_request` and
  `teardown_appcontext`, arq in `on_job_start` and `on_job_end`, and gRPC in a server interceptor.

- A decorator builds the child around each call (Typer, Celery). A unit of work with no connection
  object skips `bind` and `classify_connection` and calls `build_child_container(scope=...)` directly.

### 5. `FromDI` marker + `Dependency` resolver

`FromDI(dependency)` accepts a provider or a type and stands in for the resolved value at a handler's
call site: `x: Annotated[Foo, FromDI(foo_provider)]`. How it delivers the value depends on the
framework:

- Native-DI frameworks (FastAPI, FastMCP, FastStream, Litestar, taskiq) have a per-handler injection
  seam such as `Depends`, `Provide` or `TaskiqDepends`. `FromDI` returns that native marker, and the
  framework calls your resolver with the request container. FastMCP needs the default-value form,
  `x: T = FromDI(T)`, because it strips an injected parameter from the tool schema only when the marker
  is the default; its integration refuses to start on the `Annotated` form.
- Frameworks without request-scoped DI return an inert marker from `FromDI`, and a decorator does the
  resolution. See [the decorator path](#frameworks-without-native-di-the-decorator-path).

On the native path, `FromDI` returns the framework's marker wrapping a frozen, slotted dataclass that
holds a `modern_di.integrations.Marker`. The dataclass's `__call__` receives the request container
through the framework's DI and resolves through the marker:

```python
from modern_di import integrations

@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    marker: integrations.Marker[T_co]

    async def __call__(self, request_container: typing.Annotated[Container, myfw.Depends(build_di_container)]) -> T_co:
        return self.marker.resolve(request_container)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> T_co:  # noqa: N802
    return typing.cast(T_co, myfw.Depends(Dependency(integrations.Marker(dependency))))
```

<!-- invisible-code-block: python
app = myfw.App()
setup_di(app, Container(groups=[Dependencies]))
request = myfw.Request(app)
builder = build_di_container(request)
request_container = await anext(builder)
assert request_container.scope is Scope.REQUEST
assert request_container.resolve(myfw.Request) is request
assert isinstance(await FromDI(Dependencies.service)(request_container), MyService)
await builder.aclose()
assert request_container.closed
-->

`Marker.resolve(container)` calls `container.resolve_dependency`, so overrides, caching and
did-you-mean suggestions come with it. `FromDI` is PascalCase, with `# noqa: N802`, because it stands
in for a type at call sites.

## Lifecycle rules

- Reopen the root container on startup. A container closed on shutdown stays closed, and the next
  resolve raises `ContainerClosedError`, so a second lifespan cycle in the same process (a test client
  re-entered, a broker restarted) needs the reopen. With a context-manager lifespan, compose
  `async with container` around the existing lifespan, as `setup_di` above does: `__aenter__` opens and
  `__aexit__` closes. With callback hooks, register `container.open` on startup and
  `container.close_async` on shutdown, as FastStream, aiogram and taskiq do. `open()` validates nothing
  and is a no-op on an open container.
- Close the child container on every exit path, errors included.
- Match async and sync to the framework: `close_async` in an async framework, `close_sync` in a
  synchronous one (Typer, Flask, a sync gRPC server).
- Document that `container.validate()` goes after `setup_di`, never before. `setup_di` registers the
  connection providers, so an earlier `validate()` sees an incomplete graph and raises for any provider
  that depends on the connection object by type. Validating is optional.
- Open and close the root in every execution context the framework runs work in. Celery fires
  `worker_process_init` only for the prefork and solo pools, never for gevent, eventlet or threads,
  which run in the main worker process; its integration also hooks `worker_init` and `worker_shutdown`,
  which fire for every pool. `open()` and `close_*` are idempotent, so overlapping hooks are safe. Where
  no hook fires, work still succeeds because a new container is open, but nothing closes it and its
  finalizers never run. If the framework has no lifecycle hook at all (Flask, gRPC, Typer), the caller
  owns the root's open and close; say so on the docs page.
- On ASGI the lifespan scope is optional. A mounted sub-application never receives it from its parent,
  and some deployments turn it off (Mangum `lifespan="off"`), so call `setup_di` on the top-level
  served app or have the caller close the root.

## Scope mapping

Map each connection kind to the scope its child container opens at, following the
[scope hierarchy](../providers/scopes.md#what-each-scope-is-for):

| Unit of work | Scope | Rationale |
|---|---|---|
| HTTP request | `REQUEST` | one child per request |
| WebSocket connection | `SESSION` | outlives individual messages on the socket |
| Broker message | `REQUEST` | one child per consumed message |
| CLI command | `REQUEST` | one child per command invocation |
| Nested action within a unit | `ACTION` (a further child) | opt-in deeper scope, e.g. a Typer `action_scope` |

## How the existing integrations realize the contract

Pick the closest precedent for your framework:

| Integration | Path | Child built by | Connection providers | Root lifecycle |
|---|---|---|---|---|
| [FastAPI](fastapi.md) | native, `Depends` | async dependency generator | request, websocket | composed lifespan |
| [Litestar](litestar.md) | native, `Provide` | async dependency generator | request, websocket | `ModernDIPlugin.on_app_init` adds a lifespan |
| [FastStream](faststream.md) | native, `Depends` | `BaseMiddleware.consume_scope` | message | `on_startup` / `after_shutdown` callbacks |
| [taskiq](taskiq.md) | native, `TaskiqDepends` | async dependency generator | message | worker startup and shutdown events |
| [FastMCP](fastmcp.md) | native, default-value `FromDI` | middleware | `fastmcp.Context` | lifespan provider |
| [Starlette](starlette.md) | decorator | pure-ASGI middleware | request, websocket | composed lifespan |
| [aiohttp](aiohttp.md) | decorator | middleware | `web.Request` twice, the websocket one with `bound_type=None` | `on_startup` / `on_cleanup` signals |
| [Flask](flask.md) | decorator, or `auto_inject=True` | `before_request` / `teardown_appcontext` | request | caller |
| [aiogram](aiogram.md) | decorator, or `auto_inject=True` | dispatcher middleware | update, event | dispatcher startup and shutdown |
| [gRPC](grpc.md) | decorator | server interceptor | `ServicerContext` | caller |
| [arq](arq.md) | decorator | `on_job_start` / `on_job_end` hooks | none | wrapped `on_startup` / `on_shutdown` |
| [Celery](celery.md) | decorator, or the `DITask` base | the decorator | none | worker signals |
| [Typer](typer.md) | decorator | the decorator | none | caller |

aiohttp has one connection type for both kinds, since a WebSocket is an upgraded `web.Request`. It
tells them apart with `web.WebSocketResponse().can_prepare(request).ok` and registers only the request
provider by type.

[`modern-di-pytest`](pytest.md) has no app to wire. It exposes `modern_di_fixture` and `expose` in
place of `setup_di` and `FromDI`, and resolves from a `di_container` fixture the user defines. Follow it
for a test runner.

## Frameworks without native DI (the decorator path)

An integration can skip the decorator only where the framework evaluates a parameter default as a
provider: FastAPI, FastMCP and FastStream `Depends`, Litestar `Provide`, taskiq `TaskiqDepends`. Flask,
Starlette, aiohttp, Celery, arq, Typer and gRPC hand the handler a plain call, and aiogram matches its
`data` dict by parameter name, so those need `@inject`. Some apply it for you: Flask and aiogram take
`setup_di(..., auto_inject=True)`, and Celery has the `DITask` base class.

On this path `FromDI` is `integrations.from_di`, which returns an inert `Marker` cast to the resolved
type so checkers still see `T`. The decorator scans for markers once with `integrations.parse_markers`
at decoration time and resolves them with `integrations.resolve_markers` on each call. Here a
middleware stores the child on the connection, and `@inject` reads it back:

```python
import functools

from modern_di import integrations

FromDI = integrations.from_di

_CHILD_CONTAINER_KEY = "modern_di_container"


async def di_middleware(
    request: myfw.Request, call_next: typing.Callable[[myfw.Request], typing.Awaitable[typing.Any]]
) -> typing.Any:
    match = integrations.bind(myfw_request_provider, request)
    async with fetch_di_container(request.app).build_child_container(
        scope=match.scope, context=match.context
    ) as child:
        request.scope[_CHILD_CONTAINER_KEY] = child
        try:
            return await call_next(request)
        finally:
            del request.scope[_CHILD_CONTAINER_KEY]


def inject(func: typing.Callable[..., typing.Awaitable[typing.Any]]) -> typing.Callable[..., typing.Awaitable[typing.Any]]:
    markers = integrations.parse_markers(func)

    @functools.wraps(func)
    async def wrapper(request: myfw.Request, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        try:
            child = request.scope[_CHILD_CONTAINER_KEY]
        except KeyError:
            msg = (
                "No modern-di container found for this request. "
                "Call setup_di(app, container) so requests pass through the modern-di middleware "
                "before using @inject."
            )
            raise RuntimeError(msg) from None
        return await func(request, *args, **kwargs, **integrations.resolve_markers(child, markers))

    return wrapper


@inject
async def handler(
    request: myfw.Request, service: typing.Annotated[MyService, FromDI(Dependencies.service)]
) -> MyService:
    return service
```

<!-- invisible-code-block: python
app = myfw.App()
setup_di(app, Container(groups=[Dependencies]))
request = myfw.Request(app)
assert isinstance(await di_middleware(request, handler), MyService)
assert request.scope == {}
-->

<!-- raises: RuntimeError -->
```python
await handler(myfw.Request(app))
```

Delete the per-call entry in `finally`, as Starlette and aiohttp do. The child's context holds the
connection, so an entry left on the connection makes a reference cycle that only the garbage collector
can reclaim.

### Signature rewriting

Rewrite the signature only when the framework reads the handler's signature to bind its arguments.
Typer parses CLI options from it, Celery binds task arguments against it, and aiogram matches `data`
keys to parameter names. Starlette, aiohttp, Flask, gRPC and arq call the handler with arguments they
already know, so a plain `functools.wraps` wrapper is enough there.

When you rewrite:

- Remove the marked parameters and leave every other parameter in place, so the framework keeps
  parsing them.
- Assign the cleaned signature to `wrapper.__signature__`. `__signature__` is missing from the stubs,
  so add `# ty: ignore[unresolved-attribute]`.
- Skip `functools.wraps` when the framework unwraps `__wrapped__` to find the signature, as aiogram
  does; otherwise it reads the original signature and ignores yours.
- Add any parameter the wrapper needs to reach the container, if the handler did not declare it. Typer
  inserts a `typer.Context` at position 0 and drops it again before calling the handler.

### Pitfalls to get right

- Put the framework's registration decorator outside: `@app.command()` above `@inject`, so it
  registers the wrapper.
- Keep per-call state on a per-call store (Typer's `ctx.meta`, a request's scope), never on shared app
  state, so nested scopes can parent onto it and nothing leaks between calls.
- Guard sweeps that apply `@inject` for the user (Flask and aiogram `auto_inject`, Celery `DITask`)
  against double wrapping with `integrations.is_injected(func)` and
  `integrations.mark_injected(wrapper)`.
- Leave nested scopes to the caller. Typer's `action_scope(ctx)` yields a fresh `ACTION` child of the
  per-call container for each `with` block.

## Repo scaffolding

Each official integration is its own repository and PyPI package, with the same tooling as
`modern-di`.

- Name the repo and the PyPI package `modern-di-<framework>`, and the import package
  `modern_di_<framework>`.
- Put the implementation in `modern_di_<framework>/main.py`; a larger integration may add modules
  beside it, as aiogram does with `dialog.py`. `__init__.py` re-exports the public API and lists it in
  an explicit `__all__`, with private helpers kept out.
- In `pyproject.toml`, set `description = "modern-di integration for <Framework>"`, dependencies
  `["<framework>>=...,<...", "modern-di>=4,<5"]`, the standard classifiers, `[project.urls]` for the
  docs site and the repo, and `version = "0"`, because the release tag sets the version.
- In `tests/`:
    - `conftest.py` builds an app, calls `setup_di` with a `Container(groups=[Dependencies])`, and
      yields a test client.
    - `dependencies.py` defines a sample `Group` with providers at several scopes, plus providers that
      read the connection object to prove context injection works.
    - Cover the lifespan with a restart, resolution through `FromDI`, and websockets where the
      framework has them, under the same 100% coverage gate `modern-di` holds.
    - `test_public_surface.py` pins the package's public names.
- Ship `examples/app.py` (with an empty `examples/__init__.py`): an APP-scoped `Settings` and one
  work-scoped service that depends on it by type, resolved into one handler through the framework's
  real idiom. Use `typing.Annotated[T, FromDI(...)]`, since a `= FromDI(...)` default trips ruff
  `B008`; FastMCP is the exception and needs the default. Name the types to match the docs page.
  `tests/test_example.py` drives the example through the repo's own test double, asserts the real
  injected output, and covers the example fully, with no coverage `omit` and `# pragma: no cover` only
  on an unreachable boot line such as `if __name__ == "__main__"`.
- In the README, put a `Usage example:` line under `Full guide:` with an absolute link, such as
  `[examples/](https://github.com/modern-python/modern-di-<framework>/tree/main/examples)`. PyPI does
  not rewrite relative links.
- Copy `AGENTS.md` and the `justfile` from `modern-di`. Keep behavioural invariants in named tests, and
  record rejected alternatives on the [design decisions](../introduction/design-decisions.md#non-goals)
  page. Keep resolution sync-only and add no runtime dependency beyond the framework and `modern-di`.
  `ruff` floats forward in CI, so keep `CPY001` in the lint `ignore` list.
- In the `modern-di` repo, add `docs/integrations/<framework>.md` and a `mkdocs.yml` nav entry under
  the matching family: Web, Tasks & events, Bots, RPC, CLI or Testing. Model the page on an existing one
  such as [Starlette](starlette.md): one compact example with the same two providers as `examples/app.py`,
  `container.validate()` after `setup_di`, connection injection in its own "Framework context objects"
  section, then framework-specific sections, a `## See also` block, and the `## API` table last.
  For a provider that must also resolve outside a connection, show an optional parameter
  (`request: FrameworkType | None = None`), as the [gRPC page](grpc.md#injecting-the-servicercontext)
  does; [Optional parameters](../providers/context.md#optional-parameters) explains it.
- Releases are tag-driven: push a bare semver tag off a green `main` and the workflow publishes.

## Checklist

- [ ] Repo `modern-di-<framework>`, package `modern_di_<framework>`, `main.py` and a re-exporting
      `__init__.py` with an explicit `__all__`.
- [ ] One connection `ContextProvider` per connection kind, each mapping the kind to a scope.
- [ ] `setup_di` (or a plugin) attaches the root container, registers the connection providers, and
      wires startup and shutdown.
- [ ] `fetch_di_container` reads the root container back out of framework state.
- [ ] Every container lookup that can miss raises a `RuntimeError` naming `setup_di`, never a
      `KeyError` or `AttributeError` on a private key, and a test pins it.
- [ ] A per-unit-of-work builder opens a child container at the right scope, injects the connection as
      context, and closes it on every exit path.
- [ ] The root container reopens on startup, so a restart doesn't raise `ContainerClosedError`, and
      closes on shutdown so finalizers run.
- [ ] `close_async` or `close_sync` matches the framework.
- [ ] `FromDI` accepts `AbstractProvider[T] | type[T]` and resolves through `integrations.Marker`
      (or is `integrations.from_di` on the decorator path).
- [ ] On the decorator path, `@inject` uses `parse_markers` and `resolve_markers`, and rewrites the
      signature only if the framework binds arguments from it. See
      [the decorator path](#frameworks-without-native-di-the-decorator-path).
- [ ] Tests cover the lifespan with a restart, resolution through `FromDI`, context injection from the
      connection object, and the public surface; the coverage gate is green.
- [ ] Usage page and `mkdocs.yml` nav entry added in the `modern-di` repo.
- [ ] `examples/app.py` with a smoke test that asserts real injected output, and a README
      `Usage example:` line with an absolute link.
- [ ] `AGENTS.md` and `justfile` mirrored; invariants pinned by named tests.
