# Usage with `Starlette`

Starlette has no dependency injection of its own, so `modern-di-starlette` provides an `@inject`
decorator that fills the handler parameters marked with `FromDI`. `setup_di` installs a middleware
that gives each HTTP request a `Scope.REQUEST` child container and each websocket connection a
`Scope.SESSION` one, and wraps the app's lifespan, which closes the root container on shutdown.

## Installation

=== "uv"

    ```bash
    uv add modern-di-starlette
    ```

=== "pip"

    ```bash
    pip install modern-di-starlette
    ```

=== "poetry"

    ```bash
    poetry add modern-di-starlette
    ```

## Usage

```python
import dataclasses
import typing

from modern_di import Container, Group, Scope, providers
from modern_di_starlette import FromDI, inject, setup_di
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


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
    request: Request,
    report: typing.Annotated[Report, FromDI(Report)],
) -> JSONResponse:
    return JSONResponse(report.as_dict())


app = Starlette(routes=[Route("/report", get_report)])
container = Container(groups=[AppGroup])
setup_di(app, container)
container.validate()
```

<!-- invisible-code-block: python
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # starlette warns when httpx2 is not installed
    from starlette.testclient import TestClient

with TestClient(app) as client:
    assert client.get("/report").json() == {"service": "catalog"}
assert container.closed
container.open()
-->

Call `container.validate()` after `setup_di`. A factory that takes a Starlette `Request` depends on
the context provider that `setup_di` registers, so validating before it fails with
`ValidationFailedError`.

## Injecting into handlers

`FromDI` takes a type, as above, or a provider such as `FromDI(AppGroup.report)`. `@inject`
resolves it from the connection's child container, which it finds through the `Request` or
`WebSocket` the handler receives. A decorated handler without one among its positional arguments
raises `TypeError`, and a request that did not pass through the `setup_di` middleware raises
`RuntimeError`.

### Class-based endpoints

`@inject` works the same on the methods of an `HTTPEndpoint` or `WebSocketEndpoint` subclass.
Decorate the method, not the class. `self` and any arguments Starlette passes after the connection
are forwarded unchanged, so `WebSocketEndpoint.on_receive` and `on_disconnect` inject too:

```python
from starlette.endpoints import HTTPEndpoint, WebSocketEndpoint
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket


class ReportEndpoint(HTTPEndpoint):
    @inject
    async def get(
        self,
        request: Request,
        report: typing.Annotated[Report, FromDI(Report)],
    ) -> JSONResponse:
        return JSONResponse(report.as_dict())


class EchoEndpoint(WebSocketEndpoint):
    encoding = "text"

    @inject
    async def on_receive(
        self,
        websocket: WebSocket,
        data: str,
        settings: typing.Annotated[Settings, FromDI(Settings)],
    ) -> None:
        await websocket.send_text(f"{settings.service_name}: {data}")


app.routes.extend([Route("/report-endpoint", ReportEndpoint), WebSocketRoute("/echo", EchoEndpoint)])
```

<!-- invisible-code-block: python
with TestClient(app) as client:
    assert client.get("/report-endpoint").json() == {"service": "catalog"}
    with client.websocket_connect("/echo") as socket:
        socket.send_text("hi")
        assert socket.receive_text() == "catalog: hi"
container.open()
-->

## Scopes and lifecycle

An HTTP request gets a `Scope.REQUEST` child container and a websocket connection a
`Scope.SESSION` one; see [the scope hierarchy](../providers/scopes.md#what-each-scope-is-for). The
middleware builds the child before your handler runs and closes it once the app is done with the
connection: after the response is sent for HTTP, and when the socket closes for a websocket.

The root container is open from the moment you construct it. `setup_di` wraps the app's lifespan:
a `lifespan=` you passed to `Starlette()` stays the outer context and the state it yields passes
through, the container reopens on startup, and it closes with `close_async()` on shutdown. The
lifespan shutdown is the only thing that closes the root container.

!!! warning "Deployment: mounted sub-apps and disabled lifespan"
    A `setup_di`-wired app mounted as a sub-application (`app.mount("/sub", subapp)`) never
    receives the lifespan events from its parent, and deployments that disable lifespan (for
    example Mangum with `lifespan="off"`) skip them too. Requests still succeed, because the root
    container is open from construction, but nothing closes it, so its finalizers never run. Call
    `setup_di` on the top-level served app, or close the root yourself
    (`await container.close_async()`) at shutdown.

## Websockets

For per-message work inside a websocket's `Scope.SESSION` container, open a `Scope.REQUEST` child
of it. `FromDI(Container)` gives the handler the SESSION container:

```python
@inject
async def report_socket(
    websocket: WebSocket,
    session_container: typing.Annotated[Container, FromDI(Container)],
) -> None:
    await websocket.accept()
    async for _ in websocket.iter_text():
        async with session_container.build_child_container(scope=Scope.REQUEST) as request_container:
            report = request_container.resolve(Report)
            await websocket.send_json(report.as_dict())


app.routes.append(WebSocketRoute("/ws", report_socket))
```

<!-- invisible-code-block: python
with TestClient(app) as client, client.websocket_connect("/ws") as socket:
    socket.send_text("report")
    assert socket.receive_json() == {"service": "catalog"}
container.open()
-->

Injecting a REQUEST-scoped provider such as `FromDI(Report)` straight into a websocket handler
raises `ScopeNotInitializedError`, because no REQUEST container exists for the connection.

## Framework context objects

The integration makes `starlette.requests.Request` and `starlette.websockets.WebSocket` available
to your factories. See [Framework context objects](../providers/context.md#framework-context-objects)
for how implicit and explicit resolution work.

- `starlette_request_provider` provides the current `starlette.requests.Request` (REQUEST scope).
- `starlette_websocket_provider` provides the current `starlette.websockets.WebSocket` (SESSION scope).

The object these providers hold is one the middleware builds, so it is a different object from the
`Request` or `WebSocket` your handler receives. Both wrap the same ASGI scope and share
`request.state`.

A factory can receive the request by type, or name the provider in `kwargs`:

```python
import modern_di_starlette


def describe_request(request: Request) -> dict[str, str]:
    return {"method": request.method, "url": str(request.url)}


class RequestGroup(Group):
    by_type = providers.Factory(describe_request, scope=Scope.REQUEST, bound_type=None)
    by_provider = providers.Factory(
        describe_request,
        scope=Scope.REQUEST,
        bound_type=None,
        kwargs={"request": modern_di_starlette.starlette_request_provider},
    )
```

<!-- invisible-code-block: python
@inject
async def describe(
    request: Request,
    by_type: typing.Annotated[dict[str, str], FromDI(RequestGroup.by_type)],
    by_provider: typing.Annotated[dict[str, str], FromDI(RequestGroup.by_provider)],
) -> JSONResponse:
    return JSONResponse([by_type, by_provider])


request_app = Starlette(routes=[Route("/describe", describe)])
setup_di(request_app, Container(groups=[RequestGroup])).validate()

with TestClient(request_app) as client:
    assert client.get("/describe").json() == [{"method": "GET", "url": "http://testserver/describe"}] * 2
-->

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Async SQLAlchemy](../recipes/sqlalchemy.md): engine + session + repository through the request container.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Stores the container on `app.state`, registers the request and websocket context providers, wraps the lifespan so the container reopens on startup and closes on shutdown, and installs the middleware that builds a per-connection child container; returns the container. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-connection child container. |
| `inject` | Decorator for an `async def handler(connection: Request | WebSocket, ...)`, a function endpoint or a method of an `HTTPEndpoint` / `WebSocketEndpoint` subclass; resolves its `FromDI`-annotated parameters. Raises `TypeError` when the handler receives no `Request` or `WebSocket` positionally, and `RuntimeError` naming `setup_di` when the connection did not pass through the middleware. |
| `fetch_di_container(app)` | Returns the root `Container` stored on `app.state`. |
| `starlette_request_provider` | `ContextProvider` for `starlette.requests.Request` (REQUEST scope), auto-registered. |
| `starlette_websocket_provider` | `ContextProvider` for `starlette.websockets.WebSocket` (SESSION scope), auto-registered. |
