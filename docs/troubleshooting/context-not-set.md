# ContextProvider has no value

A `ContextProvider(SomeType)` resolves by looking up `SomeType` in the container's context registry. If no value was registered and the provider declares no `default=`, a direct resolve raises `ContextValueNotSetError`, and so does a `Factory` argument for a required parameter. A `Factory` parameter that is nullable or has a default gets that default, or `None`, instead of raising.

## Symptom

```
Cannot resolve dependency chain:
  REQUEST  MyService (myapp.ctx:9)
  caused by: No context value is set for <class 'myapp.ctx.TenantId'> (scope REQUEST), needed for argument tenant. Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider.
See: https://modern-di.modern-python.org/troubleshooting/context-not-set/
```

The top frame shows which provider failed, and the `caused by` line names the context type, the scope whose container was read, and the parameter it was needed for. A direct `container.resolve(TenantId)` raises the same error without the chain and without the `needed for argument` part. Inspect `.context_type`, `.provider_scope`, and `.parameter_name` (the parameter, or `None` for a direct resolve).

When a creator body calls `container.resolve(TenantId)` itself, the chain ends at that creator's provider and the message names no argument, because the value was not injected into a parameter.

## Cause

### 1. `set_context` was called on the wrong container (scope mismatch)

Context never propagates between containers; see [context propagation](../providers/context.md#context-propagation) for why. For a REQUEST-scoped provider, only the request container's registry is ever consulted, so setting the value on the parent has no effect, regardless of build order.

```python
# Broken: TenantId provider has scope=Scope.REQUEST, so it reads the REQUEST
# container's registry. Setting it on the APP parent does nothing.
app_container.set_context(TenantId, TenantId("acme"))     # ignored for REQUEST-scoped providers
request_container = app_container.build_child_container(scope=Scope.REQUEST)
```

To fix it, set the value on the container whose scope matches the provider's scope:

```python
# Option A: pass directly to the child when building it
request_container = app_container.build_child_container(
    scope=Scope.REQUEST,
    context={TenantId: TenantId("acme")},
)

# Option B: set on the request container after building it
request_container = app_container.build_child_container(scope=Scope.REQUEST)
request_container.set_context(TenantId, TenantId("acme"))
```

### 2. The `ContextProvider`'s scope doesn't match where you set the context

`ContextProvider(TenantId, scope=Scope.APP)` looks up the value on the APP container. If you `set_context` on the REQUEST child container, the APP-scope provider doesn't see it.

Make the scopes match. If the value is per-request, declare `ContextProvider(TenantId, scope=Scope.REQUEST)` and `set_context` on the request container (or pass via `build_child_container(context=...)`).

### 3. Framework integration didn't inject the expected request

Framework integrations (`modern-di-fastapi`, `modern-di-litestar`) register the per-request `Request`/`WebSocket` automatically. If your code expects, say, `fastapi.Request` but you're outside the framework's request lifecycle (a background task, a CLI command), no `Request` is in context and the lookup fails.

Depend on framework-injected context only inside the framework's request handling. For background tasks, build the REQUEST child container yourself and pass the necessary context.

### 4. The value is optional

If a creator runs where no value is set, such as a handler that also runs outside a request, make its parameter optional. With no value set it gets its default, or `None` for an `X | None` parameter without one:

```python
class MyService:
    def __init__(self, tenant: TenantId | None = None) -> None:
        self.tenant = tenant
```

This works for an integration's provider too, which stays required for a direct resolve. It applies only to a parameter that takes the context value itself; a parameter whose provider is another `Factory` that needs the value still raises.

To make the value optional for every consumer, direct resolves included, give the provider a default. The provider returns `default=` whenever nothing is set:

```python
tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST, default=None)
```

See [When no value is set](../providers/context.md#when-no-value-is-set).

## See also

- [Context providers](../providers/context.md) documents the full `ContextProvider` and `set_context` API.
- [Scopes](../providers/scopes.md) explains per-container context registries and why context never propagates between containers.
- [Async resources via lifespan](../recipes/async-lifespan.md) shows the canonical "construct in lifespan, inject as context" pattern.
