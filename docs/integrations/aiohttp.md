# Usage with `aiohttp`

aiohttp has no dependency-injection system of its own, so `modern-di-aiohttp`
uses the `@inject` decorator with `FromDI` markers. `setup_di` opens the root
container on app startup, closes it on cleanup, and installs middleware that
opens a per-connection child container automatically.

## How to use

### 1. Install `modern-di-aiohttp`

=== "uv"

      ```bash
      uv add modern-di-aiohttp
      ```

=== "pip"

      ```bash
      pip install modern-di-aiohttp
      ```

### 2. Apply to your application

```python
import dataclasses
import typing

from aiohttp import web
from modern_di import Container, Group, Scope, providers
from modern_di_aiohttp import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True)
class Settings:
    debug: bool = True


class AppGroup(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)


@inject
async def homepage(
    request: web.Request,
    settings: typing.Annotated[Settings, FromDI(AppGroup.settings)],
) -> web.Response:
    return web.json_response({"debug": settings.debug})


app = web.Application()
app.router.add_get("/", homepage)
setup_di(app, Container(groups=[AppGroup], validate=True))
```

### 3. Scopes

An HTTP request opens a `Scope.REQUEST` child container; a WebSocket connection
opens a `Scope.SESSION` one. Providers resolve from the connection's child
container, so `Scope.REQUEST` providers live for exactly one request.

Which scope gets opened is decided per-connection: the middleware checks the
request's handshake headers (via aiohttp's `can_prepare`), not the route or
handler. A request carrying WebSocket-upgrade headers opens a `Scope.SESSION`
child regardless of which handler ultimately serves it.

### 4. WebSockets and per-message scope

A WebSocket handler runs for the whole life of the socket, so its `Scope.SESSION`
container does too. Read the connection with `FromDI(aiohttp_websocket_provider)`.

Unlike FastAPI and Litestar, aiohttp has no separate WebSocket object — a
WebSocket is an upgraded `web.Request`. So `aiohttp_websocket_provider` binds
`web.Request` too, and is declared `bound_type=None` (not resolvable by type,
because `aiohttp_request_provider` already owns `web.Request`). That is why you
wire it **explicitly** with `FromDI(aiohttp_websocket_provider)` rather than by
type annotation.

For per-message work, open a nested `Scope.REQUEST` child of the session
container, fetched via `fetch_request_container`:

```python
import typing

from aiohttp import web
from modern_di import Scope
from modern_di_aiohttp import FromDI, aiohttp_websocket_provider, fetch_request_container, inject


@inject
async def ws_handler(
    request: web.Request,
    connection: typing.Annotated[web.Request, FromDI(aiohttp_websocket_provider)],
) -> web.WebSocketResponse:
    session_container = fetch_request_container(request)
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            async with session_container.build_child_container(scope=Scope.REQUEST) as request_container:
                ...  # resolve REQUEST-scoped providers for this message
    return ws
```

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Opens the root container on startup, closes it on cleanup, and installs the middleware that builds a per-connection child container; returns the container. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-connection child container. |
| `inject` | Decorator for an `async def handler(request: web.Request, ...)`; resolves its `FromDI`-annotated parameters. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the app. |
| `fetch_request_container(request)` | Returns the per-connection child container the middleware built (REQUEST for HTTP, SESSION for a WebSocket). |
| `aiohttp_request_provider` | `ContextProvider` for `web.Request` (REQUEST scope), auto-registered by type. |
| `aiohttp_websocket_provider` | `ContextProvider` for the WebSocket connection's `web.Request` (SESSION scope), `bound_type=None` — resolve via `FromDI(aiohttp_websocket_provider)`. |
