# ContextProvider has no value

`ContextValueNotSetError` means a `ContextProvider` was resolved, directly or for a required
parameter, on a container that holds no value for its type, and the provider has no `default=`.

## Symptom

```
modern_di.exceptions.resolution.ContextValueNotSetError: Cannot resolve dependency chain:
  REQUEST  MyService (myapp.ctx:9)
  caused by: No context value is set for <class 'myapp.ctx.TenantId'> (scope REQUEST), needed for argument tenant. Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider.
See: https://modern-di.modern-python.org/troubleshooting/context-not-set/
```

The top frame shows which provider failed, and the `caused by` line names the context type, the scope whose container was read, and the parameter it was needed for. A direct `container.resolve(TenantId)` raises the same error without the chain and without the `needed for argument` part. Inspect `.context_type`, `.provider_scope`, and `.parameter_name` (the parameter, or `None` for a direct resolve).

When a creator body calls `container.resolve(TenantId)` itself, the chain ends at that creator's provider and the message names no argument, because the value was not injected into a parameter.

## Cause

### 1. The value is set on a container of a different scope

A `ContextProvider` reads only the container of its own scope, and context never propagates between
containers; see [context propagation](../providers/context.md#context-propagation). A value set on
any other container is invisible to it, in either direction:

- A `ContextProvider(TenantId, scope=Scope.REQUEST)` does not see a value set on the APP parent.
- A `ContextProvider(TenantId, scope=Scope.APP)` does not see a value set on a REQUEST child.

<!-- invisible-code-block: python
from modern_di import Container, Scope, providers


class TenantId(str): ...


app_container = Container(scope=Scope.APP)
-->

```python
# Broken: the TenantId provider is REQUEST-scoped, so the APP value is never read.
app_container.set_context(TenantId, TenantId("acme"))
request_container = app_container.build_child_container(scope=Scope.REQUEST)
```

Set the value on the container whose scope matches the provider's scope, either when building it or
afterwards:

```python
# Works:
request_container = app_container.build_child_container(
    scope=Scope.REQUEST,
    context={TenantId: TenantId("acme")},
)

# Works:
request_container = app_container.build_child_container(scope=Scope.REQUEST)
request_container.set_context(TenantId, TenantId("acme"))
```

If the value really is per request, declare the provider with `scope=Scope.REQUEST`. If it is one
value for the whole app, declare it with `scope=Scope.APP` and set it on the APP container.

### 2. Framework integration didn't inject the expected request

Framework integrations (`modern-di-fastapi`, `modern-di-litestar`) register the per-request `Request`/`WebSocket` automatically. If your code expects, say, `fastapi.Request` but you're outside the framework's request lifecycle (a background task, a CLI command), no `Request` is in context and the lookup fails.

Depend on framework-injected context only inside the framework's request handling. For background tasks, build the REQUEST child container yourself and pass the necessary context.

### 3. The value is optional

If a creator also runs where no value is set, make its parameter optional (`tenant: TenantId | None = None`):
it then gets its default, or `None`. A parameter whose provider is another `Factory` that needs the
value still raises. See [Optional parameters](../providers/context.md#optional-parameters).

To make the value optional for every consumer, direct resolves included, give the provider a
default. See [Optional context: `default=`](../providers/context.md#optional-context-default):

```python
tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST, default=None)
```

## See also

- [Context providers](../providers/context.md): the full `ContextProvider` and `set_context` API.
- [When no value is set](../providers/context.md#when-no-value-is-set): what each kind of consumer gets.
- [Scopes](../providers/scopes.md): per-container context and why it never propagates.
- [Async resources via lifespan](../recipes/async-lifespan.md): the "construct in lifespan, inject as context" pattern.
