# Usage with `FastAPI`

*More advanced example of usage with FastAPI - [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)*

## How to use

### 1. Install `modern-di-fastapi`

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

### 2. Apply to your application
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
class RequestReport:
    settings: Settings              # APP-scoped, injected by type
    request: fastapi.Request        # REQUEST context object, injected by type

    def as_dict(self) -> dict[str, str]:
        return {
            "service": self.settings.service_name,
            "method": self.request.method,
            "path": self.request.url.path,
        }


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    request_report = providers.Factory(RequestReport, scope=Scope.REQUEST)


app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, Container(groups=[AppGroup], validate=True))


@app.get("/report")
async def report(
    request_report: typing.Annotated[RequestReport, modern_di_fastapi.FromDI(RequestReport)],
) -> dict[str, str]:
    return request_report.as_dict()
```

## Websockets

Websockets add `SESSION` scope between `APP` and `REQUEST` — see [the scope
hierarchy](../providers/scopes.md#the-scope-dependency-rule). `SESSION` covers
the lifetime of the websocket connection and is entered automatically;
`REQUEST` covers one message and must be entered manually:

```python
import typing

import fastapi
import modern_di
import modern_di_fastapi


app = fastapi.FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: fastapi.WebSocket,
    session_container: typing.Annotated[modern_di.Container, fastapi.Depends(modern_di_fastapi.build_di_container)],
) -> None:
    await websocket.accept()
    async with session_container.build_child_container(scope=modern_di.Scope.REQUEST) as request_container:
        # REQUEST scope is entered here
        # You can resolve dependencies here
        await websocket.send_text("test")

    await websocket.close()
```

## Framework Context Objects

Framework-specific context objects like `fastapi.Request` and `fastapi.WebSocket`
are automatically made available by the integration — see [Framework Context
Objects](../providers/context.md#framework-context-objects) for how implicit
and explicit resolution work.

The following context providers are available for import:

- `fastapi_request_provider` - Provides the current `fastapi.Request` object
- `fastapi_websocket_provider` - Provides the current `fastapi.WebSocket` object

### Implicit Usage (Type-based Resolution)

```python
import fastapi
from modern_di import Group, Scope, providers


def create_request_info(request: fastapi.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory automatically resolves the request dependency based on type annotation
    request_info = providers.Factory(
        create_request_info,
        scope=Scope.REQUEST,
    )
```

### Explicit Usage (Provider-based Resolution)

```python
import fastapi
import modern_di_fastapi
from modern_di import Group, Scope, providers


def create_request_info(request: fastapi.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory explicitly uses the request provider from the integration
    request_info = providers.Factory(
        create_request_info,
        scope=Scope.REQUEST,
        kwargs={"request": modern_di_fastapi.fastapi_request_provider}
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
| `setup_di(app, container)` | Registers the container on the FastAPI app and appends a lifespan that closes it on shutdown (merges with any existing `lifespan=`); returns the container. |
| `FromDI(dependency, *, use_cache=True)` | A `fastapi.Depends` wrapper that resolves a provider (or type) from the per-request child container. |
| `build_di_container(connection)` | A `fastapi.Depends` callable that yields the per-request child container — REQUEST scope for an HTTP request, SESSION scope for a WebSocket. |
| `fastapi_request_provider` | `ContextProvider` for `fastapi.Request` (REQUEST scope), auto-registered. |
| `fastapi_websocket_provider` | `ContextProvider` for `fastapi.WebSocket` (SESSION scope), auto-registered. |
