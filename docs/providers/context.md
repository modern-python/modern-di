# Context Providers

Often, scopes are connected with external events: HTTP requests, messages from a queue, callbacks from a framework.
These events can be represented by objects which can be used for dependency creation.

`ContextProvider` is a provider type that injects runtime context values — framework objects like
requests or websockets, or your own custom context — into dependencies, extracting them from the
container's context registry at resolve time.

In integrations, some context objects (like `fastapi.Request`, `litestar.WebSocket`, etc.) are
automatically provided — see [Framework Context Objects](#framework-context-objects) below.

`ContextProvider(context_type, *, scope=Scope.APP, bound_type=UNSET)` — `context_type` may also be
passed as a keyword (`context_type=`).

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
    custom_context = providers.ContextProvider(CustomContext, scope=Scope.REQUEST)

    # Factory uses the custom context
    user_info = providers.Factory(
        create_user_info,
        scope=Scope.REQUEST,
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

- Resolving it **directly** (`container.resolve(CustomContext)`) raises `ContextValueNotSetError` (see
  [Migration: direct resolve of an unset `ContextProvider` raises](../migration/to-3.x.md#5-direct-resolve-of-an-unset-contextprovider-raises)).
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

## Framework Context Objects

Every framework integration auto-registers `ContextProvider`s for its own request/websocket-like
objects — you never declare a `ContextProvider` for these yourself. Each integration builds a
per-request (or per-message, or per-connection) child container and sets the framework object as
context on it before your code resolves anything from it. There are two ways to consume that value:

**Implicit usage (type-based resolution).** Annotate a factory parameter with the framework's
type; because the integration already registered a matching `ContextProvider`, modern-di resolves
it automatically — the same mechanism as [Basic Usage](#basic-usage) above, just with the
`ContextProvider` declared by the integration instead of by you. With
[FastAPI](../integrations/fastapi.md), the `fastapi.Request` is injected into each per-request
child container automatically:

```python
from modern_di import Group, Container, Scope, providers
import fastapi
import modern_di_fastapi


def create_request_info(request: fastapi.Request | None = None) -> dict[str, str]:
    if request is None:  # only at validate() time; the integration always sets it at runtime
        return {}
    return {"method": request.method, "url": str(request.url)}


class Dependencies(Group):
    # Factory uses the request from context (automatically provided by the integration)
    request_info = providers.Factory(
        create_request_info,
        scope=Scope.REQUEST,
    )


ALL_GROUPS = [Dependencies]
app = fastapi.FastAPI()
# validate=True stays on: the optional `request` parameter (| None = None) lets
# validation skip it, since fastapi.Request's ContextProvider is only registered
# by setup_di() below — after the container (and its validate()) is built.
container = Container(groups=ALL_GROUPS, validate=True)
modern_di_fastapi.setup_di(app, container)
# The integration creates a REQUEST-scoped child container per request and
# injects the fastapi.Request into its context, so `request` is the real object
# at runtime — never None.
```

The `| None = None` on `request` is what keeps `validate=True` usable. `validate()`
runs inside the `Container(...)` call, *before* `setup_di()` registers
`fastapi.Request`'s `ContextProvider`; a required parameter with no provider would
raise [`ArgumentResolutionError`](../troubleshooting/argument-resolution-error.md).
A defaulted parameter is skipped by that check, and at runtime the integration has
registered the provider and set the per-request context, so the real `Request` is
injected — the parameter is `None` only when resolved with no context set, which the
integration never does per request. The default is load-bearing only at validation
time; it does not change runtime behaviour. (A defaulted `Factory` parameter keeps
its own disposition in modern-di 3.0 — the 3.0 `ContextValueNotSetError` affects only
a *direct* resolve of an unset context type, not a defaulted parameter, which still
falls back to its default.) Prefer this to `validate=False`, which silences *all*
validation; reach for `validate=False` (and validate after `setup_di()` instead)
only if you'd rather keep the parameter required so a missing context fails loudly.

**Explicit usage (provider-based resolution).** Every integration also exports the underlying
`ContextProvider` object itself (e.g. `fastapi_request_provider`, `litestar_request_provider`,
`aiohttp_request_provider`, `faststream_message_provider`) so you can wire it through `kwargs`
instead of relying on type-based resolution — useful with `skip_creator_parsing=True`, or when the
parameter name doesn't match the type:

```python
kwargs={"request": fastapi_request_provider}  # explicit wiring, see Factories: kwargs
```

Each integration's own page has its exact provider names, scopes, and API table:
[FastAPI](../integrations/fastapi.md#framework-context-objects),
[Litestar](../integrations/litestar.md#framework-context-objects),
[Starlette](../integrations/starlette.md#framework-context-objects),
[FastStream](../integrations/faststream.md#framework-context-objects),
[aiohttp](../integrations/aiohttp.md#api).

## See also

- [Factories](factories.md) — how factories receive injected context values.
- [Scopes](scopes.md) — choosing the scope a `ContextProvider` is bound to.
- [Container](container.md) — `build_child_container` and `set_context`.
- [FastAPI integration](../integrations/fastapi.md) — framework-provided context objects.
