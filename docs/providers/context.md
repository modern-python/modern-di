# Context providers

Often, scopes are connected with external events: HTTP requests, messages from a queue, callbacks from a framework.
These events can be represented by objects which can be used for dependency creation.

`ContextProvider` is a provider type that injects runtime context values into dependencies
(framework objects like requests or websockets, or your own custom context), extracting them from
the container's context registry at resolve time.

In integrations, some context objects (like `fastapi.Request`, `litestar.WebSocket`, etc.) are
automatically provided; see [Framework context objects](#framework-context-objects) below.

`ContextProvider(context_type, *, scope=Scope.APP, bound_type=UNSET, default=UNSET)`. The
`context_type` may also be passed as a keyword (`context_type=`).

## Basic usage

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
container = Container(groups=[Dependencies])
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

A `ContextProvider` reads its value from the context of the container at its bound scope. A context
value is required: if nothing was supplied, resolving the provider raises `ContextValueNotSetError`,
whether you resolve it directly (`container.resolve(CustomContext)`) or a `Factory` receives it as an
argument. In the second case the error also names the parameter:

```
Cannot resolve dependency chain:
  REQUEST  dict (myapp.deps:12)
  caused by: No context value is set for <class 'myapp.deps.CustomContext'> (scope REQUEST), needed for argument custom_context. Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider.
See: https://modern-di.modern-python.org/troubleshooting/context-not-set/
```

The consuming parameter's annotation and default are ignored: a creator parameter written
`custom_context: CustomContext | None = None` still raises when a `ContextProvider` backs it and no
value is set. See [ContextProvider has no value](../troubleshooting/context-not-set.md).

### Optional context: `default=`

To make a context value optional, give the provider a default. It returns `default=` whenever no
value is set, and the set value otherwise:

```python
class Dependencies(Group):
    custom_context = providers.ContextProvider(CustomContext, scope=Scope.REQUEST, default=None)
```

`default=` is the only way to make context optional. The provider returns the default object itself
on every unset resolve; it does not call or copy it.

When the provider belongs to someone else, such as an integration's provider for `fastapi.Request`,
declare a second `ContextProvider` for the same type in your app and pass it explicitly.
`bound_type=None` keeps it out of type-based wiring, so it does not collide with the integration's
provider. Both read the same context registry entry:

```python
import fastapi
from modern_di import Group, Scope, providers


def choose_engine(
    *,
    primary_engine: Engine,
    replica_engine: Engine | None,
    request: fastapi.Request | None = None,
) -> Engine:
    if replica_engine and request and request.method in REPLICA_METHODS:
        return replica_engine
    return primary_engine


class Dependencies(Group):
    optional_request = providers.ContextProvider(
        fastapi.Request, scope=Scope.REQUEST, bound_type=None, default=None
    )
    dynamic_engine = providers.Factory(
        choose_engine,
        scope=Scope.REQUEST,
        kwargs={
            "primary_engine": primary_engine,
            "replica_engine": replica_engine,
            "request": optional_request,
        },
    )
```

Inside a request, `dynamic_engine` gets the real `Request`. Where no request is set, for example in
a FastStream consumer that shares the container, it gets `None`. The integration's own provider
stays required, so `container.resolve(fastapi.Request)` outside a request still raises.

## Context propagation

Context never propagates between containers. A `ContextProvider` reads the context registry of the container **at the provider's own scope**; build order is irrelevant.

Each container copies the `context=` dict it is built with, so containers built from one dict do not share values, and `set_context()` never writes into your dict.

!!! warning "Scope determines which container is read, not timing"
    Setting context on a parent container never reaches a child-scoped provider, regardless of when you call `set_context`:

    ```python
    # Broken: a REQUEST-scoped provider reads the REQUEST container's registry.
    # Setting it on the APP parent has no effect.
    app_container = Container()
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

## Framework context objects

Every framework integration auto-registers `ContextProvider`s for its own request/websocket-like
objects, so you never declare a `ContextProvider` for these yourself. Each integration builds a
per-request (or per-message, or per-connection) child container and sets the framework object as
context on it before your code resolves anything from it. There are two ways to consume that value:

For implicit, type-based resolution, annotate a factory parameter with the framework's
type; because the integration already registered a matching `ContextProvider`, modern-di resolves
it automatically. It is the same mechanism as [Basic usage](#basic-usage) above, with the
`ContextProvider` declared by the integration instead of by you. With
[FastAPI](../integrations/fastapi.md), the `fastapi.Request` is injected into each per-request
child container automatically:

```python
from modern_di import Group, Container, Scope, providers
import fastapi
import modern_di_fastapi


def create_request_info(request: fastapi.Request) -> dict[str, str]:
    return {"method": request.method, "url": str(request.url)}


class Dependencies(Group):
    # Factory uses the request from context (automatically provided by the integration)
    request_info = providers.Factory(
        create_request_info,
        scope=Scope.REQUEST,
    )


ALL_GROUPS = [Dependencies]
app = fastapi.FastAPI()
container = Container(groups=ALL_GROUPS)
modern_di_fastapi.setup_di(app, container)
# setup_di() registers fastapi.Request's ContextProvider, so the graph is complete
# from here on — call validate() after this line, not before.
container.validate()
# The integration creates a REQUEST-scoped child container per request and
# injects the fastapi.Request into its context, so `request` is the real object
# at runtime.
```

Nothing validates automatically, so the ordering above is what matters: `fastapi.Request`'s
`ContextProvider` only exists once `setup_di()` has registered it, so calling
`container.validate()` before that line would raise
[`ValidationFailedError`](../troubleshooting/validation-failed-error.md), and its `.errors` would
carry an [`ArgumentResolutionError`](../troubleshooting/argument-resolution-error.md) for the
required `request` parameter, since the provider isn't there yet. Call `validate()` after
`setup_di()`, as above, and a required parameter validates cleanly. See [Writing an
integration](../integrations/writing-integrations.md#lifecycle-rules) for the same rule from the
integration author's side.

If you need to validate the rest of the graph before `setup_di()` runs (e.g. as part of a
narrower, construction-time check), make the parameter optional instead
(`request: fastapi.Request | None = None`), so `validate()` skips it while no provider for
`fastapi.Request` is registered; at runtime the integration still injects the real `Request`,
since it always sets the per-request context before resolving. Once `setup_di()` has registered
the provider, the parameter's default no longer applies: resolving the factory where no request is
set raises `ContextValueNotSetError` (see [When no value is set](#when-no-value-is-set) above). Use
an [app-owned optional provider](#optional-context-default) for a factory that must also work
outside a request.

For explicit, provider-based resolution, every integration also exports the underlying
`ContextProvider` object itself (e.g. `fastapi_request_provider`, `litestar_request_provider`,
`aiohttp_request_provider`, `faststream_message_provider`) so you can wire it through `kwargs`
instead of relying on type-based resolution. This is useful with `skip_creator_parsing=True`, or
when the parameter name doesn't match the type:

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

- [Factories](factories.md): how factories receive injected context values.
- [Scopes](scopes.md): choosing the scope a `ContextProvider` is bound to.
- [Container](container.md): `build_child_container` and `set_context`.
- [FastAPI integration](../integrations/fastapi.md): framework-provided context objects.
