# Usage with `Litestar`

*More advanced example of usage with LiteStar - [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)*

## How to use

1. Install `modern-di-litestar`:

=== "uv"

      ```bash
      uv add modern-di-litestar
      ```

=== "pip"

      ```bash
      pip install modern-di-litestar
      ```

=== "poetry"

      ```bash
      poetry add modern-di-litestar
      ```

2. Apply this code example to your application:
```python
import datetime
import typing

from litestar import Litestar, get
import modern_di_litestar
from modern_di import Container, Group, Scope, providers


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=create_singleton,
        cache_settings=providers.CacheSettings()
    )


# Register your groups
ALL_GROUPS = [AppGroup]


@get("/", dependencies={"injected": modern_di_litestar.FromDI(datetime.datetime)})  # Resolve by type
async def index(injected: datetime.datetime) -> str:
    return injected.isoformat()


app = Litestar(
    route_handlers=[index],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=ALL_GROUPS))],
)
```

## Websockets

Usually our application uses only two scopes: `APP` and `REQUEST`.

But when websockets are used, `SESSION` scope is used as well:
- for the lifetime of websocket-connection we have `SESSION` scope
- for each message we have `REQUEST` scope

`APP` → `SESSION` → `REQUEST`

`SESSION` scope is entered automatically.
`REQUEST` scope must be entered manually:

```python
import litestar
from modern_di import Container, Scope
import modern_di_litestar


app = litestar.Litestar(plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=ALL_GROUPS))])


@litestar.websocket_listener("/ws")
async def websocket_handler(
    data: str,
    di_container: Container
) -> None:
    request_container = di_container.build_child_container(scope=Scope.REQUEST)
    # REQUEST scope is entered here
    # You can resolve dependencies here
    pass

app.register(websocket_handler)
```

## Framework Context Objects

Framework-specific context objects like `litestar.Request` and `litestar.WebSocket` are automatically made available by the integration. You can reference these context providers in your factories either implicitly through type annotations or explicitly by importing them.

The following context providers are available for import:
- `litestar_request_provider` - Provides the current `litestar.Request` object
- `litestar_websocket_provider` - Provides the current `litestar.WebSocket` object

### Implicit Usage (Type-based Resolution)

In many cases, you can rely on automatic dependency resolution based on type annotations:

```python
import litestar
from modern_di import Group, providers, Scope


def create_request_info(request: litestar.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory automatically resolves the request dependency based on type annotation
    request_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_request_info,
    )
```

### Explicit Usage (Provider-based Resolution)

For more control, you can explicitly reference the context providers:

```python
import litestar
import modern_di_litestar
from modern_di import Group, providers, Scope


def create_request_info(request: litestar.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory explicitly uses the request provider from the integration
    request_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_request_info,
        kwargs={"request": modern_di_litestar.litestar_request_provider}
    )
```
