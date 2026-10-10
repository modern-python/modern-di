# Usage with `aiohttp`

aiohttp has no dependency injection of its own, so `modern-di-aiohttp` provides an `@inject`
decorator that fills the handler parameters marked with `FromDI`. `setup_di` installs a middleware
that gives each HTTP request a `Scope.REQUEST` child container and each websocket connection a
`Scope.SESSION` one. It also hooks the app's startup and cleanup signals, and the cleanup closes
the root container.

## Installation

=== "uv"

    ```bash
    uv add modern-di-aiohttp
    ```

=== "pip"

    ```bash
    pip install modern-di-aiohttp
    ```

=== "poetry"

    ```bash
    poetry add modern-di-aiohttp
    ```

## Usage

```python
import dataclasses
import typing

from aiohttp import web
from modern_di import Container, Group, Scope, providers
from modern_di_aiohttp import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings   # APP-scoped, injected by type

    def as_dict(self) -> dict[str, str]:
        return {"service": self.settings.service_name}


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


@inject
async def get_report(
    request: web.Request,
    report: typing.Annotated[Report, FromDI(Report)],
) -> web.Response:
    return web.json_response(report.as_dict())


app = web.Application()
app.router.add_get("/report", get_report)
container = Container(groups=[AppGroup])
setup_di(app, container)
container.validate()
```

Call `container.validate()` after `setup_di`. A factory that takes a `web.Request` depends on the
context provider that `setup_di` registers, so validating before it fails with
`ValidationFailedError`.

## Injecting into handlers

`FromDI` takes a type, as above, or a provider such as `FromDI(AppGroup.report)`. `@inject`
resolves it from the connection's child container, which it finds through the `web.Request` the
handler receives. A decorated handler without one among its positional arguments raises
`TypeError`, and a request that did not pass through the `setup_di` middleware raises
`RuntimeError`.

### Class-based views

`@inject` works the same on the methods of a `web.View` subclass. Decorate the method, not the
class. aiohttp calls the method with no arguments and keeps the request on `self.request`, which
is where the decorator reads it from:

```python
class ReportView(web.View):
    @inject
    async def get(
        self,
        report: typing.Annotated[Report, FromDI(Report)],
    ) -> web.Response:
        return web.json_response(report.as_dict())


app.router.add_view("/report-view", ReportView)
```

## Scopes and lifecycle

An HTTP request gets a `Scope.REQUEST` child container and a websocket connection a
`Scope.SESSION` one; see [the scope hierarchy](../providers/scopes.md#what-each-scope-is-for). The
middleware builds the child before the handler runs and closes it when the handler returns.

The middleware picks the scope from the request's handshake headers, using aiohttp's
`can_prepare`, not from the route or handler. A request that carries websocket-upgrade headers gets
a `Scope.SESSION` child whichever handler serves it. An HTTP-only handler that injects a
REQUEST-scoped provider then fails with `ScopeNotInitializedError`, and the client gets a 500.

The root container is open from the moment you construct it. `setup_di` reopens it on startup and
closes it with `close_async()` on cleanup. An app attached with `add_subapp` receives both signals
from its parent, so a `setup_di`-wired sub-app is closed too.

## Websockets

A websocket handler runs for the whole life of the socket, and so does its `Scope.SESSION`
container. `FromDI(Container)` gives the handler that container, as does
`fetch_request_container(request)`. For per-message work, open a `Scope.REQUEST` child of it:

```python
@inject
async def report_socket(
    request: web.Request,
    session_container: typing.Annotated[Container, FromDI(Container)],
) -> web.WebSocketResponse:
    socket = web.WebSocketResponse()
    await socket.prepare(request)
    async for message in socket:
        if message.type == web.WSMsgType.TEXT:
            async with session_container.build_child_container(scope=Scope.REQUEST) as request_container:
                await socket.send_json(request_container.resolve(Report).as_dict())
    return socket


app.router.add_get("/ws", report_socket)
```

<!-- invisible-code-block: python
import warnings

from aiohttp.test_utils import TestClient, TestServer

with warnings.catch_warnings():
    warnings.simplefilter("ignore", web.NotAppKeyWarning)  # modern-di-aiohttp stores the child under a str key
    async with TestClient(TestServer(app)) as client:
        for path in ("/report", "/report-view"):
            response = await client.get(path)
            assert await response.json() == {"service": "catalog"}
        async with client.ws_connect("/ws") as socket:
            await socket.send_str("report")
            assert await socket.receive_json() == {"service": "catalog"}
assert container.closed
-->

Injecting a REQUEST-scoped provider such as `FromDI(Report)` straight into a websocket handler
raises `ScopeNotInitializedError`, because no REQUEST container exists for the connection.

## Framework context objects

The integration makes the current `web.Request` available to your factories. See
[Framework context objects](../providers/context.md#framework-context-objects) for how implicit
and explicit resolution work.

- `aiohttp_request_provider` provides the current `web.Request` of an HTTP request (REQUEST
  scope). It is registered by type.
- `aiohttp_websocket_provider` provides the `web.Request` of a websocket connection (SESSION
  scope). aiohttp has no separate websocket object, and `aiohttp_request_provider` already owns the
  `web.Request` type, so this provider is declared with `bound_type=None`: only a reference to it
  resolves.

A factory that takes `request: web.Request` by type resolves only inside an HTTP request. In a
websocket handler the type still points at `aiohttp_request_provider`, which a websocket connection
never sets: resolving from the SESSION container raises `ScopeNotInitializedError`, and from a
per-message REQUEST child `ContextValueNotSetError`. A factory meant for websocket connections
names `aiohttp_websocket_provider` in `kwargs` and is SESSION-scoped:

```python
from modern_di_aiohttp import aiohttp_request_provider, aiohttp_websocket_provider


def describe_request(request: web.Request) -> dict[str, str]:
    return {"method": request.method, "path": request.path}


class RequestGroup(Group):
    by_type = providers.Factory(describe_request, scope=Scope.REQUEST, bound_type=None)
    by_provider = providers.Factory(
        describe_request,
        scope=Scope.REQUEST,
        bound_type=None,
        kwargs={"request": aiohttp_request_provider},
    )
    for_websocket = providers.Factory(
        describe_request,
        scope=Scope.SESSION,
        bound_type=None,
        kwargs={"request": aiohttp_websocket_provider},
    )
```

<!-- invisible-code-block: python
@inject
async def describe(
    request: web.Request,
    by_type: typing.Annotated[dict[str, str], FromDI(RequestGroup.by_type)],
    by_provider: typing.Annotated[dict[str, str], FromDI(RequestGroup.by_provider)],
) -> web.Response:
    return web.json_response([by_type, by_provider])


@inject
async def describe_socket(
    request: web.Request,
    for_websocket: typing.Annotated[dict[str, str], FromDI(RequestGroup.for_websocket)],
) -> web.WebSocketResponse:
    socket = web.WebSocketResponse()
    await socket.prepare(request)
    await socket.send_json(for_websocket)
    await socket.close()
    return socket


request_app = web.Application()
request_app.router.add_get("/describe", describe)
request_app.router.add_get("/describe-ws", describe_socket)
setup_di(request_app, Container(groups=[RequestGroup])).validate()

with warnings.catch_warnings():
    warnings.simplefilter("ignore", web.NotAppKeyWarning)
    async with TestClient(TestServer(request_app)) as client:
        response = await client.get("/describe")
        assert await response.json() == [{"method": "GET", "path": "/describe"}] * 2
        async with client.ws_connect("/describe-ws") as socket:
            assert await socket.receive_json() == {"method": "GET", "path": "/describe-ws"}
-->

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Async SQLAlchemy](../recipes/sqlalchemy.md): engine + session + repository through the request container.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Stores the container on the app, registers the request and websocket context providers, reopens the container on startup and closes it on cleanup, and installs the middleware that builds a per-connection child container; returns the container. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-connection child container. |
| `inject` | Decorator for an `async def handler(request: web.Request, ...)`, a function handler or a method of a `web.View` subclass; resolves its `FromDI`-annotated parameters. Raises `TypeError` when the handler receives neither a `web.Request` nor a `web.View`, and `RuntimeError` naming `setup_di` when the request did not pass through the middleware. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the app. |
| `fetch_request_container(request)` | Returns the per-connection child container the middleware built (REQUEST for HTTP, SESSION for a websocket). Raises `RuntimeError` naming `setup_di` when the request did not pass through the middleware. |
| `aiohttp_request_provider` | `ContextProvider` for `web.Request` (REQUEST scope), auto-registered by type. |
| `aiohttp_websocket_provider` | `ContextProvider` for the websocket connection's `web.Request` (SESSION scope), `bound_type=None`; resolve it via `FromDI(aiohttp_websocket_provider)` or a `kwargs` reference. |
