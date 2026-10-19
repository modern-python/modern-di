# Usage with `Litestar`

`modern-di-litestar` builds on Litestar's own dependency injection. `FromDI` returns a Litestar
`Provide`, which you list in a route's `dependencies` like any other, and the handler declares the
parameter with `NamedDependency[...]`. `ModernDIPlugin` gives each HTTP request a `Scope.REQUEST`
child container and each websocket connection a `Scope.SESSION` one, and adds lifespan hooks that
reopen the root container on startup and close it on shutdown.

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

Call `container.validate()` after `Litestar(...)` is constructed. The plugin registers its context
providers in `on_app_init`, which Litestar runs during construction, and a factory that takes a
`litestar.Request` depends on one of them, so validating before that fails with
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
    The name `di_container` is reserved for the plugin's own dependency, which every `FromDI`
    depends on. Since modern-di-litestar 4.0.1, an autowired group that declares a provider under
    that name raises `litestar.exceptions.ImproperlyConfiguredException` when the app is created.
    Earlier releases replace the plugin's dependency, and Litestar never finishes building the app.

With `autowired_groups` set, `FromDI` on a route can still take a type. Pass a provider instance
only for providers outside `autowired_groups`: Litestar rejects one provider registered under two
keys and raises `ImproperlyConfiguredException`.

## Scopes and lifecycle

An HTTP request gets a `Scope.REQUEST` child container and a websocket connection a
`Scope.SESSION` one; see [the scope hierarchy](../providers/scopes.md#what-each-scope-is-for). The
child is a Litestar generator dependency, so it is built only for handlers that inject something
and closed in Litestar's dependency cleanup. The close is shielded from cancellation, so a request
cancelled by an anyio scope such as `move_on_after` still runs its finalizers. A close that takes
longer than 10 seconds is abandoned, with a warning on the `modern_di_litestar.main` logger.

The root container is open from the moment you construct it. The plugin puts a manager first in
the app's `lifespan` list, which reopens the container on startup, and a hook last in `on_shutdown`,
which closes it with `close_async()`. Since modern-di-litestar 4.2.0, the container opens before
your other lifespan code and closes after all your shutdown code, so your `lifespan` managers and
`on_startup` and `on_shutdown` hooks can resolve APP-scoped dependencies, and APP finalizers run
last. Earlier releases closed it before your `on_shutdown` hooks ran. The order holds for code
passed to `Litestar(...)` or added by an `on_app_init` handler or a plugin listed before
`ModernDIPlugin`. A plugin listed after it can still add a manager ahead of it or a shutdown hook
behind it.

The shutdown hook is the only thing that closes the root container, so when the server skips the
lifespan, requests still succeed but its finalizers never run. Close it yourself
(`await container.close_async()`) at shutdown in that case.

Since modern-di-litestar 4.1.0, `ModernDIPlugin(container, manage_lifespan=False)` adds neither
hook and leaves the root container's open and close to you, for a container shared with another
app; see [Lifecycle](../providers/lifecycle.md#closing-and-reopening).

### Streaming responses

Litestar runs dependency cleanup when the handler returns, before it sends the response, so the
child container is already closed while a `Stream` or `ServerSentEvent` body runs. A REQUEST-scoped
instance the handler got through `FromDI` has been finalized by then. A database session would be
closed, for example. To use REQUEST-scoped dependencies in the body, open a REQUEST child of the
root container inside the generator:

```python
import collections.abc

from litestar.response import Stream


@litestar.get("/report-stream")
async def stream_report(request: litestar.Request) -> Stream:
    async def body() -> collections.abc.AsyncIterator[str]:
        root = modern_di_litestar.fetch_di_container(request.app)
        async with root.build_child_container(scope=Scope.REQUEST) as request_container:
            yield request_container.resolve(Report).as_dict()["service"]

    return Stream(body())


stream_app = litestar.Litestar(
    route_handlers=[stream_report],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=[AppGroup]))],
)
```

<!-- invisible-code-block: python
with TestClient(stream_app) as client:
    assert client.get("/report-stream").text == "catalog"
-->

That child closes when the generator finishes. It has no `litestar.Request` in its context, so a
factory that takes the request cannot be resolved from it. Pass the values such a factory needs
into the generator instead.

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
- [Organize a large container with multiple Groups](../recipes/multi-group.md): splitting providers across groups, with `autowired_groups`.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `ModernDIPlugin(container, autowired_groups=None, *, manage_lifespan=True)` | Litestar `InitPlugin` that stores the container on the app state, registers the request and websocket context providers and the `di_container` dependency, puts a manager first in `lifespan` that reopens the container and a hook last in `on_shutdown` that closes it (neither with `manage_lifespan=False`), and (if `autowired_groups` is given) exposes each provider in those groups as a Litestar dependency keyed by attribute name. |
| `FromDI(dependency)` | Returns a Litestar `Provide` that resolves a provider or type from the connection's child container (REQUEST for HTTP, SESSION for a websocket). |
| `di_container` | The dependency name the plugin registers for the connection's child container; declare `di_container: NamedDependency[Container]` to receive it. |
| `fetch_di_container(app)` | Returns the root `Container` stored on the Litestar app. |
| `litestar_request_provider` | `ContextProvider` for `litestar.Request` (REQUEST scope), auto-registered. |
| `litestar_websocket_provider` | `ContextProvider` for `litestar.WebSocket` (SESSION scope), auto-registered. |
