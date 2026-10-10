# Usage with `Litestar`

`modern-di-litestar` builds on Litestar's own dependency injection. `FromDI` returns a Litestar
`Provide`, which you list in a route's `dependencies` like any other, and the handler declares the
parameter with `NamedDependency[...]`. `ModernDIPlugin` gives each HTTP request a `Scope.REQUEST`
child container and each websocket connection a `Scope.SESSION` one, and adds a lifespan hook that
closes the root container on shutdown.

*More advanced example of usage with Litestar: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)*

## Installation

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

## Usage

```python
import dataclasses

import litestar
import modern_di_litestar
from litestar.di import NamedDependency
from modern_di import Container, Group, Scope, providers


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


@litestar.get("/report", dependencies={"report": modern_di_litestar.FromDI(Report)})
async def get_report(report: NamedDependency[Report]) -> dict[str, str]:
    return report.as_dict()


container = Container(groups=[AppGroup])
app = litestar.Litestar(
    route_handlers=[get_report],
    plugins=[modern_di_litestar.ModernDIPlugin(container)],
)
container.validate()
```

<!-- invisible-code-block: python
from litestar.testing import TestClient

with TestClient(app) as client:
    assert client.get("/report").json() == {"service": "catalog"}
assert container.closed
container.open()
-->

Mark every injected parameter with `NamedDependency[...]` from `litestar.di`. Litestar 2.23
deprecated inferring a dependency from a plain annotation, and Litestar 3.0 removes it.

Call `container.validate()` after the plugin is installed. A factory that takes a `litestar.Request`
depends on the context provider that the plugin registers, so validating before it fails with
`ValidationFailedError`.

## Injecting into handlers

`FromDI` takes a type, as above, or a provider such as `FromDI(AppGroup.report)`, and resolves it
from the connection's child container. The `dependencies` mapping can sit on a route, a controller,
a router or the app, as with any Litestar dependency.

The plugin also registers a `di_container` dependency, the connection's child container itself. A
handler receives it by declaring `di_container: NamedDependency[Container]`, with no `FromDI`.

### Auto-wiring with `autowired_groups`

Pass `autowired_groups` to `ModernDIPlugin` to register every provider in those groups as a Litestar
dependency, keyed by its attribute name. A handler then receives a provider by naming a parameter
after it, with no per-route `FromDI`:

```python
@litestar.get("/autowired-report")
async def get_autowired_report(report: NamedDependency[Report]) -> dict[str, str]:
    return report.as_dict()


autowired_app = litestar.Litestar(
    route_handlers=[get_autowired_report],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=[AppGroup]), autowired_groups=[AppGroup])],
)
```

<!-- invisible-code-block: python
with TestClient(autowired_app) as client:
    assert client.get("/autowired-report").json() == {"service": "catalog"}
-->

If an attribute name appears in more than one group, or matches a dependency the app already has, a
`UserWarning` is emitted and the autowired provider overwrites the earlier one; among groups, the
last one wins.

!!! warning "Don't name a provider `di_container`"
    An autowired provider named `di_container` replaces the plugin's own container dependency,
    which every `FromDI` depends on. Litestar then fails to build the app with `RecursionError`.

With `autowired_groups` set, `FromDI` on a route can still take a type. Pass a provider instance
only for providers outside `autowired_groups`: Litestar rejects one provider registered under two
keys and raises `ImproperlyConfiguredException`.

## Scopes and lifecycle

An HTTP request gets a `Scope.REQUEST` child container and a websocket connection a
`Scope.SESSION` one; see [the scope hierarchy](../providers/scopes.md#what-each-scope-is-for). The
child is a Litestar generator dependency, so it is built only for handlers that inject something
and closed in Litestar's dependency cleanup.

The root container is open from the moment you construct it. The plugin appends a lifespan hook
that reopens it on startup and closes it with `close_async()` on shutdown. That hook is the only
thing that closes the root container, so when the server skips the lifespan, requests still
succeed but its finalizers never run. Close it yourself (`await container.close_async()`) at
shutdown in that case.

## Websockets

In a websocket handler, `di_container` is the connection's `Scope.SESSION` container, which lives
as long as the connection. For per-message work, open a `Scope.REQUEST` child of it:

```python
@litestar.websocket_listener("/ws")
async def report_socket(data: str, di_container: NamedDependency[Container]) -> dict[str, str]:
    async with di_container.build_child_container(scope=Scope.REQUEST) as request_container:
        return request_container.resolve(Report).as_dict()


websocket_app = litestar.Litestar(
    route_handlers=[report_socket],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=[AppGroup]))],
)
```

<!-- invisible-code-block: python
with TestClient(websocket_app) as client, client.websocket_connect("/ws") as socket:
    socket.send_text("report")
    assert socket.receive_json() == {"service": "catalog"}
-->

Injecting a REQUEST-scoped provider such as `FromDI(Report)` straight into a websocket handler
raises `ScopeNotInitializedError`, because no REQUEST container exists for the connection.

## Framework context objects

The integration makes `litestar.Request` and `litestar.WebSocket` available to your factories. See
[Framework context objects](../providers/context.md#framework-context-objects) for how implicit
and explicit resolution work.

- `litestar_request_provider` provides the current `litestar.Request` (REQUEST scope).
- `litestar_websocket_provider` provides the current `litestar.WebSocket` (SESSION scope).

A factory can receive the request by type, or name the provider in `kwargs`:

```python
def describe_request(request: litestar.Request) -> dict[str, str]:
    return {"method": request.method, "url": str(request.url)}


class RequestGroup(Group):
    by_type = providers.Factory(describe_request, scope=Scope.REQUEST, bound_type=None)
    by_provider = providers.Factory(
        describe_request,
        scope=Scope.REQUEST,
        bound_type=None,
        kwargs={"request": modern_di_litestar.litestar_request_provider},
    )
```

<!-- invisible-code-block: python
@litestar.get(
    "/describe",
    dependencies={
        "by_type": modern_di_litestar.FromDI(RequestGroup.by_type),
        "by_provider": modern_di_litestar.FromDI(RequestGroup.by_provider),
    },
)
async def describe(
    by_type: NamedDependency[dict[str, str]], by_provider: NamedDependency[dict[str, str]]
) -> list[dict[str, str]]:
    return [by_type, by_provider]


request_container = Container(groups=[RequestGroup])
request_app = litestar.Litestar(
    route_handlers=[describe], plugins=[modern_di_litestar.ModernDIPlugin(request_container)]
)
request_container.validate()

with TestClient(request_app) as client:
    assert client.get("/describe").json() == [{"method": "GET", "url": "http://testserver.local/describe"}] * 2
-->

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Multi-group organization](../recipes/multi-group.md): splitting providers across groups, with `autowired_groups`.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `ModernDIPlugin(container, autowired_groups=None)` | Litestar `InitPlugin` that stores the container on the app state, registers the request and websocket context providers and the `di_container` dependency, appends a lifespan hook that closes the container on shutdown, and (if `autowired_groups` is given) exposes each provider in those groups as a Litestar dependency keyed by attribute name. |
| `FromDI(dependency)` | Returns a Litestar `Provide` that resolves a provider or type from the connection's child container (REQUEST for HTTP, SESSION for a websocket). |
| `di_container` | The dependency name the plugin registers for the connection's child container; declare `di_container: NamedDependency[Container]` to receive it. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the Litestar app. |
| `litestar_request_provider` | `ContextProvider` for `litestar.Request` (REQUEST scope), auto-registered. |
| `litestar_websocket_provider` | `ContextProvider` for `litestar.WebSocket` (SESSION scope), auto-registered. |
