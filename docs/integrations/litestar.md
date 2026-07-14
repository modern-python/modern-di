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
import dataclasses

import litestar
import modern_di_litestar
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class RequestReport:
    settings: Settings           # APP-scoped, injected by type
    request: litestar.Request    # REQUEST context object, injected by type

    def as_dict(self) -> dict[str, str]:
        return {
            "service": self.settings.service_name,
            "method": self.request.method,
            "path": self.request.url.path,
        }


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    request_report = providers.Factory(RequestReport, scope=Scope.REQUEST)


@litestar.get("/report", dependencies={"report": modern_di_litestar.FromDI(RequestReport)})
async def report(report: RequestReport) -> dict[str, str]:
    return report.as_dict()


app = litestar.Litestar(
    route_handlers=[report],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=[AppGroup], validate=True))],
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
    user_repo = providers.Factory(UserRepository, scope=Scope.REQUEST)


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

Websockets add `SESSION` scope between `APP` and `REQUEST` — see [the scope
hierarchy](../providers/scopes.md#the-scope-dependency-rule). `SESSION` covers
the lifetime of the websocket connection and is entered automatically;
`REQUEST` covers one message and must be entered manually:

```python
import dataclasses
import litestar
from modern_di import Container, Group, Scope, providers
import modern_di_litestar


@dataclasses.dataclass
class MyService:
    async def handle(self, data: str) -> None: ...


class Dependencies(Group):
    my_service = providers.Factory(MyService, scope=Scope.REQUEST)


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

Framework-specific context objects like `litestar.Request` and `litestar.WebSocket`
are automatically made available by the integration — see [Framework Context
Objects](../providers/context.md#framework-context-objects) for how implicit
and explicit resolution work.

The following context providers are available for import:

- `litestar_request_provider` - Provides the current `litestar.Request` object
- `litestar_websocket_provider` - Provides the current `litestar.WebSocket` object

### Implicit Usage (Type-based Resolution)

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
        create_request_info,
        scope=Scope.REQUEST,
    )
```

### Explicit Usage (Provider-based Resolution)

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
        create_request_info,
        scope=Scope.REQUEST,
        kwargs={"request": modern_di_litestar.litestar_request_provider}
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
| `ModernDIPlugin(container, autowired_groups=None)` | Litestar `InitPlugin` that registers the container, composes the lifespan, and (if `autowired_groups` is given) exposes each provider in those groups as a Litestar dependency keyed by attribute name. |
| `FromDI(dependency)` | Returns a Litestar `Provide` that resolves a provider or type from the per-request child container. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the Litestar app. |
| `litestar_request_provider` | `ContextProvider` for `litestar.Request` (REQUEST scope), auto-registered. |
| `litestar_websocket_provider` | `ContextProvider` for `litestar.WebSocket` (SESSION scope), auto-registered. |
