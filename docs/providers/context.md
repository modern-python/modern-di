# Context providers

Often, scopes are connected with external events: HTTP requests, messages from a queue, callbacks from a framework.
These events can be represented by objects which can be used for dependency creation.

`ContextProvider` is a provider type that injects runtime context values into dependencies
(framework objects like requests or websockets, or your own custom context), extracting them from
the container's context at resolve time.

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

A `ContextProvider` reads its value from the context of the container at its bound scope. When
nothing was supplied, the result depends on how the value is used:

- A direct resolve (`container.resolve(CustomContext)`) raises `ContextValueNotSetError`.
- A `Factory` argument for a parameter that is nullable or has a default gets that default, or
  `None` for an `X | None` parameter without one.
- A `Factory` argument for a required parameter raises `ContextValueNotSetError`, and the error
  names the parameter:

```
Cannot resolve dependency chain:
  REQUEST  dict (myapp.deps:12)
  caused by: No context value is set for <class 'myapp.deps.CustomContext'> (scope REQUEST), needed for argument custom_context. Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider.
See: https://modern-di.modern-python.org/troubleshooting/context-not-set/
```

A provider declared with [`default=`](#optional-context-default) returns its default in all three
cases. See [ContextProvider has no value](../troubleshooting/context-not-set.md).

### Optional parameters

Make the parameter optional when a creator runs both with and without the value. This works with
an integration's provider too. With `modern-di-fastapi` set up, `fastapi.Request` is wired by type
to the integration's provider:

```python
import fastapi
from modern_di import Group, Scope, providers


class AuditLog:
    def __init__(self, request: fastapi.Request | None = None) -> None:
        self.client_host = request.client.host if request and request.client else None


class Dependencies(Group):
    audit_log = providers.Factory(AuditLog, scope=Scope.REQUEST)
```

Inside a request, `AuditLog` gets the real `Request`. Where no request is set, for example in a
FastStream consumer that shares the container, it gets `None`. The integration's provider stays
required, so `container.resolve(fastapi.Request)` outside a request still raises.

The parameter decides this however it is wired: by type, by a member of a union, through an
`Alias`, or with `kwargs={...}`. It applies only to an argument that comes straight from the
`ContextProvider`. If the parameter's provider is a `Factory` that itself needs the missing value,
the resolve raises. A creator with `skip_creator_parsing=True` or a `**kwargs` signature has no
parsed parameters, so its context arguments never fall back.

A cached factory built while the value was unset keeps the fallback value for the lifetime of its
container. A later `set_context()` does not rebuild it.

### Optional context: `default=`

To make a context value optional for every consumer, direct resolves and required parameters
included, give the provider a default. It returns `default=` whenever no value is set, and the set
value otherwise:

```python
class Dependencies(Group):
    custom_context = providers.ContextProvider(CustomContext, scope=Scope.REQUEST, default=None)
```

The provider's default wins over a parameter's default. The provider returns the default object
itself on every unset resolve; it does not call or copy it. Type checkers see `default=None` too:
the provider above is a `ContextProvider[CustomContext | None]`.

## Context propagation

Context never propagates between containers. A `ContextProvider` reads the context of the container **at the provider's own scope**; build order is irrelevant.

Each container copies the `context=` dict it is built with, so containers built from one dict do not share values, and `set_context()` never writes into your dict.

!!! warning "Scope determines which container is read, not timing"
    Setting context on a parent container never reaches a child-scoped provider, regardless of when you call `set_context`:

    <!-- skip: next "fragment" -->

    ```python
    # Broken: a REQUEST-scoped provider reads the REQUEST container's registry.
    # Setting it on the APP parent has no effect.
    app_container = Container()
    app_container.set_context(CustomContext, value)  # ignored for REQUEST-scoped providers
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    ```

    For a REQUEST-scoped `ContextProvider`, set the value on the request container:

    <!-- skip: next "fragment" -->

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
[`ValidationFailedError`](../troubleshooting/validation-failed-error.md), and its `.exceptions` would
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
the provider, resolving the factory where no request is set gives it `None` (see
[Optional parameters](#optional-parameters) above).

For explicit, provider-based resolution, every integration also exports the underlying
`ContextProvider` object itself (e.g. `fastapi_request_provider`, `litestar_request_provider`,
`aiohttp_request_provider`, `faststream_message_provider`) so you can wire it through `kwargs`
instead of relying on type-based resolution. This is useful with `skip_creator_parsing=True`, or
when the parameter name doesn't match the type:

<!-- skip: next "continues the FastAPI example above" -->

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
