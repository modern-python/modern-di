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
import datetime
import contextlib
import typing

import fastapi
import modern_di_fastapi
from modern_di import Container, Group, Scope, providers


app = fastapi.FastAPI()


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Factory(
        create_singleton,
        scope=Scope.APP,
        cache=True
    )


# Register your groups
ALL_GROUPS = [AppGroup]

# Setup DI with your groups
modern_di_fastapi.setup_di(app, Container(groups=ALL_GROUPS, validate=True))


@app.get("/")
async def read_root(
    instance: typing.Annotated[
        datetime.datetime,
        modern_di_fastapi.FromDI(datetime.datetime),  # Resolve by type instead of provider
    ],
) -> datetime.datetime:
    return instance

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

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Registers the container on the FastAPI app and appends a lifespan that closes it on shutdown (merges with any existing `lifespan=`); returns the container. |
| `FromDI(dependency, *, use_cache=True)` | A `fastapi.Depends` wrapper that resolves a provider (or type) from the per-request child container. |
| `build_di_container(connection)` | A `fastapi.Depends` callable that yields the per-request child container — REQUEST scope for an HTTP request, SESSION scope for a WebSocket. |
| `fastapi_request_provider` | `ContextProvider` for `fastapi.Request` (REQUEST scope), auto-registered. |
| `fastapi_websocket_provider` | `ContextProvider` for `fastapi.WebSocket` (SESSION scope), auto-registered. |
