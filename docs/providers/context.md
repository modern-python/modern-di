# Context providers

A `ContextProvider` injects a value that exists only at runtime, such as an HTTP request, a queue
message or the current tenant, and each container gets that value from whoever builds it. Framework
integrations declare these providers for their own request and message objects; see
[Framework context objects](#framework-context-objects).

`ContextProvider(context_type, *, scope=UNSET, bound_type=UNSET, default=UNSET)`. The
`context_type` may also be passed as a keyword (`context_type=`).

- `scope`: the scope of the container whose context the provider reads. Left unset, it takes the
  [group's default scope](scopes.md#group-level-default-scope), or `Scope.APP` when the group has
  none.
- `bound_type`: the type the provider is registered under, `context_type` by default. Set it to
  `None` to make the provider resolvable by reference only. Values are always keyed by
  `context_type` in `context=` and `set_context()`, whatever `bound_type` is.
- `default`: what the provider returns when no value is set; see
  [Optional context: `default=`](#optional-context-default).

## Basic usage

Declare a `ContextProvider` for your context type, supply the value when you build the child
container, and any [`Factory`](factories.md) that takes that type as a parameter receives it:

```python
import dataclasses

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class CustomContext:
    user_id: str
    tenant_id: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UserInfo:
    user_id: str
    tenant_id: str


def create_user_info(custom_context: CustomContext) -> UserInfo:
    return UserInfo(user_id=custom_context.user_id, tenant_id=custom_context.tenant_id)


class Dependencies(Group):
    custom_context = providers.ContextProvider(CustomContext, scope=Scope.REQUEST)
    user_info = providers.Factory(create_user_info, scope=Scope.REQUEST)


container = Container(groups=[Dependencies])
request_container = container.build_child_container(
    scope=Scope.REQUEST,
    context={CustomContext: CustomContext(user_id="123", tenant_id="abc")},
)

user_info = request_container.resolve(UserInfo)
assert user_info == UserInfo(user_id="123", tenant_id="abc")
```

The root container takes the same argument, `Container(context={...})`, for APP-scoped values, and
`container.set_context(CustomContext, value)` sets a value on a container after it is built. A
`context=` entry only supplies a value: without a declared `ContextProvider` for that type,
resolving it raises `ProviderNotRegisteredError`.

## When no value is set

A `ContextProvider` reads its value from the context of the container at its own scope. When
nothing was supplied, the result depends on how the value is used:

- A direct resolve (`container.resolve(CustomContext)`) raises `ContextValueNotSetError`.
- A `Factory` argument for a parameter that is nullable or has a default gets that default, or
  `None` for an `X | None` parameter without one.
- A `Factory` argument for a required parameter raises `ContextValueNotSetError`, and the error
  names the parameter:

```
Cannot resolve dependency chain:
  REQUEST  UserInfo (myapp.deps:18)
  caused by: No context value is set for <class 'myapp.deps.CustomContext'> (scope REQUEST), needed for argument custom_context. Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider.
See: https://modern-di.modern-python.org/troubleshooting/context-not-set/
```

A provider declared with [`default=`](#optional-context-default) returns its default in all three
cases. See [ContextProvider has no value](../troubleshooting/context-not-set.md).

### Optional parameters

Make the parameter optional when a creator runs both with and without the value:

```python
class Request:
    def __init__(self, client_host: str) -> None:
        self.client_host = client_host


class AuditLog:
    def __init__(self, request: Request | None = None) -> None:
        self.client_host = request.client_host if request else None


class WebDependencies(Group, scope=Scope.REQUEST):
    request = providers.ContextProvider(Request)
    audit_log = providers.Factory(AuditLog)


web_container = Container(groups=[WebDependencies])

without_request = web_container.build_child_container(scope=Scope.REQUEST)
assert without_request.resolve(AuditLog).client_host is None

with_request = web_container.build_child_container(
    scope=Scope.REQUEST, context={Request: Request("10.0.0.1")}
)
assert with_request.resolve(AuditLog).client_host == "10.0.0.1"
```

The same works with an integration's provider. With `modern-di-fastapi` set up, an
`AuditLog(request: fastapi.Request | None = None)` gets the real request inside a FastAPI handler
and `None` in a FastStream consumer that shares the container. The provider itself stays required,
so `container.resolve(fastapi.Request)` outside a request still raises.

The fallback has limits:

- It applies however the parameter is wired: by type, by a member of a union, through an `Alias`,
  or with `kwargs={...}`.
- It applies only to an argument that comes straight from the `ContextProvider`. If the
  parameter's provider is a `Factory` that itself needs the missing value, the resolve raises.
- A creator with `skip_creator_parsing=True` or a `**kwargs` signature has no parsed parameters,
  so its context arguments never fall back.
- A cached factory built while the value was unset keeps the fallback value for the lifetime of
  its container. A later `set_context()` does not rebuild it.

### Optional context: `default=`

To make a context value optional for every consumer, direct resolves and required parameters
included, give the provider a default. It returns `default=` whenever no value is set, and the set
value otherwise:

```python
GUEST = CustomContext(user_id="guest", tenant_id="public")


class GuestDependencies(Group):
    custom_context = providers.ContextProvider(CustomContext, scope=Scope.REQUEST, default=GUEST)
    user_info = providers.Factory(create_user_info, scope=Scope.REQUEST)


guest_container = Container(groups=[GuestDependencies])
anonymous = guest_container.build_child_container(scope=Scope.REQUEST)

assert anonymous.resolve(CustomContext) is GUEST
assert anonymous.resolve(UserInfo) == UserInfo(user_id="guest", tenant_id="public")
```

The provider's default wins over a parameter's default. The provider returns the default object
itself on every unset resolve, without calling or copying it. Type checkers see `default=None` too:
`ContextProvider(CustomContext, default=None)` is a `ContextProvider[CustomContext | None]`.

## Context propagation

Context never propagates between containers. A `ContextProvider` reads only the context of the
container at its own scope (see [Resolving across scopes](scopes.md#resolving-across-scopes)), so
build order and the direction of the hop make no difference. Each container copies the `context=`
dict it is built with, so containers built from one dict do not share values, and `set_context()`
never writes into your dict.

<!-- invisible-code-block: python
value = CustomContext(user_id="123", tenant_id="abc")
-->

!!! warning "Scope determines which container is read, not timing"
    Setting context on a parent container never reaches a child-scoped provider, regardless of when you call `set_context`:

    ```python
    # Broken: a REQUEST-scoped provider reads the REQUEST container's context.
    # Setting it on the APP parent has no effect.
    app_container = Container()
    app_container.set_context(CustomContext, value)
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    ```

    For a REQUEST-scoped `ContextProvider`, set the value on the request container:

    ```python
    # Works: pass context directly when building the child
    request_container = app_container.build_child_container(
        scope=Scope.REQUEST, context={CustomContext: value}
    )

    # Works: set it on the request container after building it
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.set_context(CustomContext, value)
    ```

The rule holds in the other direction too. An APP-scoped provider ignores a value passed to a
child's `context=`, and a REQUEST-scoped provider resolved from an ACTION child reads the REQUEST
container even when the ACTION child has a value of its own:

```python
@dataclasses.dataclass(frozen=True)
class Settings:
    source: str


@dataclasses.dataclass(frozen=True)
class Tenant:
    source: str


class Propagation(Group):
    settings = providers.ContextProvider(Settings, scope=Scope.APP)
    tenant = providers.ContextProvider(Tenant, scope=Scope.REQUEST)


root = Container(groups=[Propagation], context={Settings: Settings("app")})
request = root.build_child_container(
    scope=Scope.REQUEST, context={Settings: Settings("request"), Tenant: Tenant("request")}
)
action = request.build_child_container(scope=Scope.ACTION, context={Tenant: Tenant("action")})

assert request.resolve(Settings).source == "app"
assert action.resolve(Tenant).source == "request"
```

## Framework context objects

Most integrations register `ContextProvider`s for their framework's request, websocket, message or
call objects: aiohttp, aiogram, FastAPI, FastMCP, FastStream, Flask, gRPC, Litestar, Starlette and
taskiq. arq, Celery and Typer register none. The provider is registered by the integration's setup
call (`setup_di()`, or constructing `DIInterceptor` for gRPC), and the integration seeds each
per-request (or per-message, or per-call) child container's context with the framework object
before your code resolves from it.

To consume the value by type, annotate a factory parameter with the framework's type. It is the
same mechanism as [Basic usage](#basic-usage), with the `ContextProvider` declared by the
integration instead of by you. The graph is complete only once the setup call has registered the
provider, so `validate()` raises before it and passes after. Here `add_providers` stands in for
`setup_di()`:

```python
request_provider = providers.ContextProvider(Request, scope=Scope.REQUEST)


@dataclasses.dataclass(frozen=True)
class ClientInfo:
    host: str


def create_client_info(request: Request) -> ClientInfo:
    return ClientInfo(host=request.client_host)


class Handlers(Group):
    client_info = providers.Factory(create_client_info, scope=Scope.REQUEST)


app_container = Container(groups=[Handlers])
```

<!-- raises: ValidationFailedError -->

```python
app_container.validate()
```

```python
app_container.add_providers(request_provider)
app_container.validate()
```

Call `validate()` after the setup call; see
[Writing an integration](../integrations/writing-integrations.md#lifecycle-rules) and
[Validation](lifecycle.md#validation). A parameter typed `Request | None = None` validates either
way, as in [Optional parameters](#optional-parameters).

To wire the value explicitly, use the `ContextProvider` object the integration exports (for example
`fastapi_request_provider`, `litestar_request_provider`, `aiohttp_request_provider` or
`faststream_message_provider`) in `kwargs`. This helps with `skip_creator_parsing=True`, or when
the parameter is not annotated with the framework type:

<!-- invisible-code-block: python
try:
    from modern_di_fastapi import fastapi_request_provider
except ModuleNotFoundError:
    fastapi_request_provider = None
-->

```python
kwargs={"request": fastapi_request_provider}  # explicit wiring, see Factories: kwargs
```

Each integration's page lists its provider names, scopes and types:
[aiohttp](../integrations/aiohttp.md#api),
[aiogram](../integrations/aiogram.md#framework-context-objects),
[FastAPI](../integrations/fastapi.md#framework-context-objects),
[FastMCP](../integrations/fastmcp.md#framework-context-objects),
[FastStream](../integrations/faststream.md#framework-context-objects),
[Flask](../integrations/flask.md#framework-context-objects),
[gRPC](../integrations/grpc.md#injecting-the-servicercontext),
[Litestar](../integrations/litestar.md#framework-context-objects),
[Starlette](../integrations/starlette.md#framework-context-objects),
[taskiq](../integrations/taskiq.md#framework-context-objects).

## See also

- [Factories](factories.md) — how factories receive injected context values.
- [Scopes](scopes.md) — choosing the scope a `ContextProvider` is bound to.
- [Container](container.md) — building containers with `context=`, and where `set_context` and
  `build_child_container` are covered.
- [ContextProvider has no value](../troubleshooting/context-not-set.md) — fixing
  `ContextValueNotSetError`.
- [Writing an integration](../integrations/writing-integrations.md) — how an integration registers
  its providers and seeds the context.
