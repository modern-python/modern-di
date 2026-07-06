# Usage with `Litestar`

*More advanced example of usage with Litestar - [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)*

## How to use

### 1. Install `modern-di-litestar`

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

### 2. Apply to your application
```python
import datetime

from litestar import Litestar, get
import modern_di_litestar
from modern_di import Container, Group, Scope, providers


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=create_singleton,
        cache=True
    )


# Register your groups
ALL_GROUPS = [AppGroup]


@get("/", dependencies={"injected": modern_di_litestar.FromDI(datetime.datetime)})  # Resolve by type
async def index(injected: datetime.datetime) -> str:
    return injected.isoformat()


app = Litestar(
    route_handlers=[index],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=ALL_GROUPS, validate=True))],
)
```

### Auto-wiring with `autowired_groups`

Pass `autowired_groups` to `ModernDIPlugin` to automatically register every provider in those groups as a Litestar dependency, keyed by its attribute name. This lets route handlers declare dependencies as plain parameters without per-route `FromDI` calls:

```python
import dataclasses
import litestar
from modern_di import Container, Group, Scope, providers
from modern_di_litestar import ModernDIPlugin


@dataclasses.dataclass(kw_only=True)
class UserRepository:
    pass


class AppGroup(Group):
    user_repo = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)


ALL_GROUPS = [AppGroup]

app = litestar.Litestar(
    plugins=[ModernDIPlugin(Container(groups=ALL_GROUPS, validate=True), autowired_groups=ALL_GROUPS)],
)


@litestar.get("/users")
async def list_users(user_repo: UserRepository) -> list[str]:
    ...
```

If the same attribute name appears in multiple groups, a `UserWarning` is emitted and the last group's provider wins.

## Websockets

Usually our application uses only two scopes: `APP` and `REQUEST`.

But when websockets are used, `SESSION` scope is used as well:

- for the lifetime of websocket-connection we have `SESSION` scope
- for each message we have `REQUEST` scope

`APP` → `SESSION` → `REQUEST`

`SESSION` scope is entered automatically.
`REQUEST` scope must be entered manually:

```python
import dataclasses
import litestar
from modern_di import Container, Group, Scope, providers
import modern_di_litestar


@dataclasses.dataclass
class MyService:
    async def handle(self, data: str) -> None: ...


class Dependencies(Group):
    my_service = providers.Factory(scope=Scope.REQUEST, creator=MyService)


ALL_GROUPS = [Dependencies]

app = litestar.Litestar(plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=ALL_GROUPS, validate=True))])


@litestar.websocket_listener("/ws")
async def websocket_handler(
    data: str,
    di_container: Container,  # auto-resolved — the plugin registers a "di_container" dependency
) -> None:
    # For a websocket, di_container is the SESSION-scoped child; enter REQUEST scope here
    async with di_container.build_child_container(scope=Scope.REQUEST) as request_container:
        service = request_container.resolve(MyService)
        await service.handle(data)


app.register(websocket_handler)
```

`di_container` is injected by name — the plugin registers it as a Litestar dependency, so you don't need a `FromDI` marker for the container itself.

## Framework Context Objects

Framework-specific context objects like `litestar.Request` and `litestar.WebSocket` are automatically made available by the integration.
You can reference these context providers in your factories either implicitly through type annotations or explicitly by importing them.

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

## API

| Symbol | Description |
|---|---|
| `ModernDIPlugin(container, autowired_groups=None)` | Litestar `InitPlugin` that registers the container, composes the lifespan, and (if `autowired_groups` is given) exposes each provider in those groups as a Litestar dependency keyed by attribute name. |
| `FromDI(dependency)` | Returns a Litestar `Provide` that resolves a provider or type from the per-request child container. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the Litestar app. |
| `litestar_request_provider` | `ContextProvider` for `litestar.Request` (REQUEST scope), auto-registered. |
| `litestar_websocket_provider` | `ContextProvider` for `litestar.WebSocket` (SESSION scope), auto-registered. |
