# Context Providers

Often, scopes are connected with external events: HTTP requests, messages from a queue, callbacks from a framework.
These events can be represented by objects which can be used for dependency creation.

`ContextProvider` is a provider type that allows injecting context values into dependencies.
This is particularly useful for injecting framework-specific objects like requests, websockets, etc.

ContextProvider makes context data available to other providers in your dependency graph by extracting values from the container's context.

In integrations, some context objects (like `fastapi.Request`, `litestar.WebSocket`, etc.) are automatically provided.

## Basic Usage

Declare a `ContextProvider` for your context type, supply the value when you build the child container, and any [`Factory`](factories.md) that takes that type as a parameter receives it automatically:

```python
from modern_di import Group, Container, Scope, providers

# Custom context type
class CustomContext:
    def __init__(self, user_id: str, tenant_id: str) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id


def create_user_info(custom_context: CustomContext) -> dict[str, str]:
    return {
        "user_id": custom_context.user_id,
        "tenant_id": custom_context.tenant_id,
    }


class Dependencies(Group):
    # Manually defined ContextProvider for custom context
    custom_context = providers.ContextProvider(scope=Scope.REQUEST, context_type=CustomContext)

    # Factory uses the custom context
    user_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_user_info,
    )


# Provide custom context when building the child container
container = Container(groups=[Dependencies], validate=True)
custom_context = CustomContext(user_id="123", tenant_id="abc")
request_container = container.build_child_container(
    scope=Scope.REQUEST,
    context={CustomContext: custom_context}
)

# Now resolve the factory — it will receive the custom context automatically
user_info = request_container.resolve_provider(Dependencies.user_info)
# {"user_id": "123", "tenant_id": "abc"}
```

The provider is bound to a [scope](scopes.md) (here `Scope.REQUEST`) and the value is supplied via
[`build_child_container(context={...})`](container.md).

## When no value is set

A `ContextProvider` reads its value from the context of the container at its bound scope. If nothing was supplied, behavior depends on the call path:

- Resolving it **directly** (`container.resolve(CustomContext)`) returns `None`.
- Injecting it into a `Factory` parameter that is **not** `Optional`/defaulted raises `ArgumentResolutionError`.

Annotate the consuming parameter as `X | None` (or give it a default) if the value can legitimately be absent. See [ContextProvider has no value](../troubleshooting/context-not-set.md).

## Context propagation

Context never propagates between containers. A `ContextProvider` reads the context registry of the container **at the provider's own scope** — build order is irrelevant.

!!! warning "Scope determines which container is read, not timing"
    Setting context on a parent container never reaches a child-scoped provider, regardless of when you call `set_context`:

    ```python
    # ❌ Broken: a REQUEST-scoped provider reads the REQUEST container's registry.
    # Setting it on the APP parent has no effect.
    app_container = Container(validate=True)
    app_container.set_context(CustomContext, value)  # ignored for REQUEST-scoped providers
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    ```

    For a REQUEST-scoped `ContextProvider`, set the value on the request container:

    ```python
    # Option A: pass context directly when building the child
    request_container = app_container.build_child_container(
        scope=Scope.REQUEST, context={CustomContext: value}
    )

    # Option B: set on the request container after building it
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.set_context(CustomContext, value)
    ```

    Setting context on the parent only works when the `ContextProvider`'s scope matches the parent's scope.

## With a framework integration

Integrations register context providers for their own request/websocket objects, so you don't declare them yourself. With [FastAPI](../integrations/fastapi.md), the `fastapi.Request` is injected into each per-request child container automatically:

```python
from modern_di import Group, Container, Scope, providers
import fastapi
import modern_di_fastapi


def create_request_info(request: fastapi.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class Dependencies(Group):
    # Factory uses the request from context (automatically provided by the integration)
    request_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_request_info,
    )


ALL_GROUPS = [Dependencies]
app = fastapi.FastAPI()
# validate=False: request_info depends on fastapi.Request, whose ContextProvider
# is registered by setup_di() below — validating before that call would raise
# ArgumentResolutionError for a dependency the integration hasn't wired in yet.
container = Container(groups=ALL_GROUPS, validate=False)
modern_di_fastapi.setup_di(app, container)
# The integration creates a REQUEST-scoped child container per request and
# automatically injects the fastapi.Request into its context. The factory
# is resolved from the child container, not the APP-scope container.
```

## See also

- [Factories](factories.md) — how factories receive injected context values.
- [Scopes](scopes.md) — choosing the scope a `ContextProvider` is bound to.
- [Container](container.md) — `build_child_container` and `set_context`.
- [FastAPI integration](../integrations/fastapi.md) — framework-provided context objects.
