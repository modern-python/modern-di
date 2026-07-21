# Usage with `Starlette`

Starlette has no dependency-injection system of its own, so `modern-di-starlette`
uses the `@inject` decorator with `FromDI` markers (there is no `Depends`).
`setup_di` composes the lifespan and installs middleware that opens a
per-connection child container automatically.

## How to use

### 1. Install `modern-di-starlette`

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

### 2. Apply to your application

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
setup_di(app, Container(groups=[AppGroup], validate=True))
```

!!! warning "Deployment: mounted sub-apps and disabled lifespan"
    Starlette only opens the root container from the ASGI **lifespan** event.
    A `setup_di`-wired app **mounted as a sub-application**
    (`app.mount("/sub", subapp)`) never receives that event from its parent,
    and deployments that disable lifespan (e.g. Mangum `lifespan="off"`) skip
    it too — the first request then raises `ContainerClosedError`. Call
    `setup_di` on the **top-level served app**, or open the root yourself
    (`container.open()` / `with`) before serving.

### 3. Scopes

See [the scope hierarchy](../providers/scopes.md#the-scope-dependency-rule) —
an HTTP request opens a `Scope.REQUEST` child container; a WebSocket connection
opens a `Scope.SESSION` one, built by the middleware before your handler runs
and kept open for the whole life of the connection.

## Websockets

For per-message work within a websocket's `Scope.SESSION` container, open a
nested `Scope.REQUEST` child:

```python
import typing

import modern_di
from modern_di import Scope, providers
from modern_di_starlette import FromDI, inject
from starlette.websockets import WebSocket


@inject
async def ws_handler(
    websocket: WebSocket,
    container: typing.Annotated[modern_di.Container, FromDI(providers.container_provider)],
) -> None:
    await websocket.accept()
    async for message in websocket.iter_text():
        async with container.build_child_container(scope=Scope.REQUEST) as request_container:
            ...  # resolve REQUEST-scoped providers for this message
```

## Framework Context Objects

Framework-specific context objects like `starlette.requests.Request` and
`starlette.websockets.WebSocket` are automatically made available by the
integration — see [Framework Context Objects](../providers/context.md#framework-context-objects)
for how implicit and explicit resolution work.

The following context providers are available for import:

- `starlette_request_provider` — the current `starlette.requests.Request` (REQUEST scope)
- `starlette_websocket_provider` — the current `starlette.websockets.WebSocket` (SESSION scope)

### Implicit Usage (Type-based Resolution)

```python
from starlette.requests import Request
from modern_di import Group, Scope, providers


def create_request_info(request: Request) -> dict[str, str]:
    return {"method": request.method, "url": str(request.url)}


class AppGroup(Group):
    request_info = providers.Factory(create_request_info, scope=Scope.REQUEST)
```

### Explicit Usage (Provider-based Resolution)

```python
import modern_di_starlette
from starlette.requests import Request
from modern_di import Group, Scope, providers


def create_request_info(request: Request) -> dict[str, str]:
    return {"method": request.method, "url": str(request.url)}


class AppGroup(Group):
    request_info = providers.Factory(
        create_request_info,
        scope=Scope.REQUEST,
        kwargs={"request": modern_di_starlette.starlette_request_provider},
    )
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md) — swap providers in your tests.
- [Async SQLAlchemy](../recipes/sqlalchemy.md) — engine + session + repository through the request container.
- [Lifecycle](../providers/lifecycle.md) — finalizers and `close_async()`.
- [Scopes](../providers/scopes.md) — the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Registers the container on `app.state`, composes the lifespan (opens/closes the container), and installs the middleware that builds a per-connection child container; returns the container. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-connection child container. |
| `inject` | Decorator for an `async def handler(connection: Request | WebSocket, ...)`; resolves its `FromDI`-annotated parameters. |
| `fetch_di_container(app)` | Returns the root `Container` stored on `app.state`. |
| `starlette_request_provider` | `ContextProvider` for `starlette.requests.Request` (REQUEST scope), auto-registered. |
| `starlette_websocket_provider` | `ContextProvider` for `starlette.websockets.WebSocket` (SESSION scope), auto-registered. |
