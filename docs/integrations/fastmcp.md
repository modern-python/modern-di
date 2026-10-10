# Usage with `FastMCP`

## How to use

### 1. Install `modern-di-fastmcp`

=== "uv"

    ```bash
    uv add modern-di-fastmcp
    ```

=== "pip"

    ```bash
    pip install modern-di-fastmcp
    ```

=== "poetry"

    ```bash
    poetry add modern-di-fastmcp
    ```

### 2. Apply to your server

```python
import dataclasses

import fastmcp
import modern_di_fastmcp
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    greeting: str = "Hello"


@dataclasses.dataclass(kw_only=True, slots=True)
class GreetingService:
    settings: Settings   # APP-scoped, injected by type

    def greet(self, name: str) -> str:
        return f"{self.settings.greeting}, {name}!"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    service = providers.Factory(GreetingService, scope=Scope.REQUEST)


mcp = fastmcp.FastMCP("greeter")
container = Container(groups=[AppGroup])
modern_di_fastmcp.setup_di(mcp, container)
container.validate()  # after setup_di: its connection provider is now registered


@mcp.tool
def greet(name: str, service: GreetingService = modern_di_fastmcp.FromDI(GreetingService)) -> str:  # noqa: B008
    return service.greet(name)
```

The same `FromDI` default works on `@mcp.resource`, resource templates and `@mcp.prompt`. FastMCP
leaves injected parameters out of the schema it sends to the client, so a client never sees or
supplies them.

### `FromDI` is a default value

Unlike the other integrations, `FromDI` is the parameter's default, `x: T = FromDI(T)`, and not
`Annotated` metadata. FastMCP keeps an `Annotated` parameter in the schema and asks the client for
its value. When the parameter's type has no schema, as with a plain class, FastMCP refuses the tool
when it is defined. When it has one, as with a dataclass, the server raises `TypeError` at startup
naming the parameter. That check covers the server's own tools, resources and prompts; components
of a mounted server, and components added after startup, are not checked.

Ruff's B008 flags a call in a default. Add `FromDI` to bugbear's immutable calls instead of writing
`# noqa: B008` on every parameter:

```toml
[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["modern_di_fastmcp.FromDI"]
```

## Scopes

`setup_di` opens the APP container when the server's lifespan starts and closes it with
`close_async()` when the lifespan ends. A middleware opens a `Scope.REQUEST` child for every MCP
request: a tool call, a resource read, a prompt render or a list call. Notifications open nothing.
There is no `Scope.SESSION` child: an MCP session has no close hook, so nothing could close it.

A tool of a mounted server resolves through the parent's middleware, so call `setup_di` on the
server that clients connect to.

## Framework context objects

The current `fastmcp.Context` is available through `fastmcp_context_provider`, at `Scope.REQUEST`.
Inject it by type into a factory:

```python
@dataclasses.dataclass(kw_only=True, slots=True)
class RequestInfo:
    context: fastmcp.Context

    @property
    def request_id(self) -> str:
        return self.context.request_id


class AppGroup(Group):
    request_info = providers.Factory(RequestInfo, scope=Scope.REQUEST)
```

It is the middleware's `Context` for the request, a sibling of the one FastMCP passes to a tool
through `CurrentContext()`; both share the request's state.

## Sharing a container with FastAPI

When a FastMCP server is mounted inside a FastAPI app, one container can serve both. Exactly one
of them must own the container's lifespan, or the first to stop closes it for the other. Let
FastAPI own it and pass `manage_lifespan=False` to the FastMCP side:

```python
import fastapi
import modern_di_fastapi

modern_di_fastmcp.setup_di(mcp, container, manage_lifespan=False)

mcp_app = mcp.http_app(path="/")
app = fastapi.FastAPI(lifespan=mcp_app.lifespan)  # FastMCP's HTTP app needs its lifespan to run
modern_di_fastapi.setup_di(app, container)
app.mount("/mcp", mcp_app)
```

## Background tasks

A tool registered with `task=True` runs in FastMCP's task worker, outside middleware, so there is no
request container for it. `FromDI` raises a `RuntimeError` there that names this case.

## Testing

Use FastMCP's in-memory client. Entering it runs the server's lifespan, so the container opens and
closes with it:

```python
async with fastmcp.Client(mcp) as client:
    result = await client.call_tool("greet", {"name": "world"})
assert result.data == "Hello, world!"
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.
- [FastAPI](fastapi.md): the other side of a shared container.

## API

| Symbol | Description |
|---|---|
| `setup_di(server, container, *, manage_lifespan=True)` | Attaches the APP container to the server, registers `fastmcp_context_provider`, and adds the middleware that creates a REQUEST child container per MCP request. The server's lifespan opens the container and closes it at shutdown; `manage_lifespan=False` leaves that to another app. Raises `TypeError` at startup for a `FromDI` inside `Annotated`, and `RuntimeError` when called twice for one server. Returns the container. |
| `FromDI(dependency)` | Parameter default that resolves a provider instance or a plain type from the request container. Raises `RuntimeError` naming `setup_di` when no request container is active. |
| `fetch_di_container(server)` | Returns the APP container attached to the server; raises `RuntimeError` when `setup_di` was not called. |
| `fastmcp_context_provider` | `ContextProvider` for the current `fastmcp.Context`. |
