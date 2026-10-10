# Usage with `FastAPI`

`modern-di-fastapi` builds on FastAPI's own dependency injection: `FromDI` returns a
`fastapi.Depends`, so a handler declares an injected value the same way it declares any other
dependency. Each HTTP request gets a `Scope.REQUEST` child container and each websocket connection a
`Scope.SESSION` one. `setup_di` wraps the app's lifespan, which closes the root container on
shutdown.

*More advanced example of usage with FastAPI: [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)*

## Installation

=== "uv"

    ```bash
    uv add modern-di-fastapi
    ```

=== "pip"

    ```bash
    pip install modern-di-fastapi
    ```

=== "poetry"

    ```bash
    poetry add modern-di-fastapi
    ```

## Usage

```python
import dataclasses
import typing

import fastapi
import modern_di_fastapi
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings              # APP-scoped, injected by type

    def as_dict(self) -> dict[str, str]:
        return {"service": self.settings.service_name}


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


app = fastapi.FastAPI()
container = Container(groups=[AppGroup])
modern_di_fastapi.setup_di(app, container)
container.validate()


@app.get("/report")
async def get_report(
    report: typing.Annotated[Report, modern_di_fastapi.FromDI(Report)],
) -> dict[str, str]:
    return report.as_dict()
```

<!-- invisible-code-block: python
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # starlette warns when httpx2 is not installed
    from fastapi.testclient import TestClient

with TestClient(app) as client:
    assert client.get("/report").json() == {"service": "catalog"}
assert container.closed
container.open()
-->

Call `container.validate()` after `setup_di`. A factory that takes a `fastapi.Request` depends on
the context provider that `setup_di` registers, so validating before it fails with
`ValidationFailedError`.

## Coming from `Depends`

The [FastAPI `Depends` tab](../introduction/comparison.md#where-is-singleton-cross-framework-vocabulary)
of the vocabulary table maps each `Depends` idiom to its modern-di equivalent.

FastAPI runs the cleanup code of a `yield` dependency after the response is sent, and modern-di
closes the request container at the same point. REQUEST-scoped finalizers therefore run after the
client already has its response, so a commit that fails in a finalizer can no longer change the
status code. Commit in the handler or in a service method instead.

That ordering holds from FastAPI 0.118.0. FastAPI 0.106.0 through 0.117.x ran the cleanup before
sending the response, so on those versions a failing REQUEST-scoped finalizer turns the response
into a 500.

FastAPI's `Depends(scope="function" | "request")` decides whether the code after `yield` runs
before or after the response is sent. It needs FastAPI 0.121.0 or later. modern-di's `Scope` is
unrelated: it decides how long a cached instance lives. See [Scopes](../providers/scopes.md).

## Injecting into handlers

`FromDI` takes a type, as above, or a provider such as `FromDI(AppGroup.report)`. It resolves from
the connection's child container.

FastAPI caches a dependency for the rest of the request, so two parameters with the same `FromDI`
get one value. Pass `FromDI(..., use_cache=False)` to resolve again; an uncached factory then builds
a second instance.

To get the child container itself, use `FromDI(modern_di.Container)` or
`fastapi.Depends(modern_di_fastapi.build_di_container)`. Both return the same container.

## Scopes and lifecycle

An HTTP request gets a `Scope.REQUEST` child container and a websocket connection a
`Scope.SESSION` one; see [the scope hierarchy](../providers/scopes.md#what-each-scope-is-for).
`build_di_container` creates the child as a `yield` dependency, so a handler that injects nothing
gets no child, and FastAPI's dependency cleanup closes it.

The root container is open from the moment you construct it. `setup_di` wraps the app's lifespan:
a `lifespan=` you passed to `FastAPI()` stays the outer context and the state it yields passes
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

A websocket endpoint injects with `FromDI` too, and resolves from the connection's `Scope.SESSION`
container. That container lives as long as the connection. For per-message work, open a
`Scope.REQUEST` child of it:

```python
@app.websocket("/ws")
async def report_socket(
    websocket: fastapi.WebSocket,
    session_container: typing.Annotated[Container, modern_di_fastapi.FromDI(Container)],
) -> None:
    await websocket.accept()
    async for _ in websocket.iter_text():
        async with session_container.build_child_container(scope=Scope.REQUEST) as request_container:
            report = request_container.resolve(Report)
            await websocket.send_json(report.as_dict())
```

<!-- invisible-code-block: python
with TestClient(app) as client, client.websocket_connect("/ws") as socket:
    socket.send_text("report")
    assert socket.receive_json() == {"service": "catalog"}
container.open()
-->

Injecting a REQUEST-scoped provider such as `FromDI(Report)` straight into a websocket endpoint
raises `ScopeNotInitializedError`, because no REQUEST container exists for the connection.

## Framework context objects

The integration makes `fastapi.Request` and `fastapi.WebSocket` available to your factories. See
[Framework context objects](../providers/context.md#framework-context-objects) for how implicit
and explicit resolution work.

- `fastapi_request_provider` provides the current `fastapi.Request` (REQUEST scope).
- `fastapi_websocket_provider` provides the current `fastapi.WebSocket` (SESSION scope).

A factory can receive the request by type, or name the provider in `kwargs`:

```python
def describe_request(request: fastapi.Request) -> dict[str, str]:
    return {"method": request.method, "url": str(request.url)}


class RequestGroup(Group):
    by_type = providers.Factory(describe_request, scope=Scope.REQUEST, bound_type=None)
    by_provider = providers.Factory(
        describe_request,
        scope=Scope.REQUEST,
        bound_type=None,
        kwargs={"request": modern_di_fastapi.fastapi_request_provider},
    )
```

<!-- invisible-code-block: python
request_app = fastapi.FastAPI()
modern_di_fastapi.setup_di(request_app, Container(groups=[RequestGroup])).validate()


@request_app.get("/describe")
async def describe(
    by_type: typing.Annotated[dict[str, str], modern_di_fastapi.FromDI(RequestGroup.by_type)],
    by_provider: typing.Annotated[dict[str, str], modern_di_fastapi.FromDI(RequestGroup.by_provider)],
) -> list[dict[str, str]]:
    return [by_type, by_provider]


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
| `setup_di(app, container)` | Stores the container on the app, registers the request and websocket context providers, and wraps the app's lifespan (any `lifespan=` you passed included) so the container reopens on startup and closes on shutdown; returns the container. |
| `FromDI(dependency, *, use_cache=True)` | A `fastapi.Depends` that resolves a provider or type from the connection's child container (REQUEST for HTTP, SESSION for a websocket). Raises `RuntimeError` naming `setup_di` when a request reaches it without `setup_di` called. |
| `build_di_container(connection)` | A `fastapi.Depends` callable that yields the connection's child container: REQUEST scope for an HTTP request, SESSION scope for a websocket. |
| `fastapi_request_provider` | `ContextProvider` for `fastapi.Request` (REQUEST scope), auto-registered. |
| `fastapi_websocket_provider` | `ContextProvider` for `fastapi.WebSocket` (SESSION scope), auto-registered. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the app. Raises `RuntimeError` naming `setup_di` when called on an app without `setup_di` called. |
