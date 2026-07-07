# ContextProvider has no value

A `ContextProvider(context_type=SomeType)` resolves by looking up `SomeType` in the container's context registry. If no value was registered, the outcome depends on how the provider is consumed: resolving it directly returns `None`, while injecting it into a `Factory` parameter that has no value raises `ArgumentResolutionError` — **unless** that parameter has a default (the default is used; `None` is not injected) or is nullable `X | None` (then `None` is injected).

## Understanding the error

```
Cannot resolve dependency chain:
  REQUEST  MyService
  caused by: Argument tenant of type <class 'TenantId'> cannot be resolved. Trying to build dependency <class 'MyService'>.
```

The error is an `ArgumentResolutionError` rendered as a chain: the top frame shows which provider failed, and the `caused by` line names the specific parameter that could not be wired. The parameter cannot be resolved because the `ContextProvider` for `TenantId` has no value in this container's context registry — nothing was set for that type on this container.

## Common causes

### 1. `set_context` was called on the wrong container (scope mismatch)

Context never propagates between containers — see [context propagation](../providers/context.md#context-propagation) for why. For a REQUEST-scoped provider, only the request container's registry is ever consulted — setting the value on the parent has no effect, regardless of build order.

```python
# ❌ Broken: TenantId provider has scope=Scope.REQUEST, so it reads the REQUEST
# container's registry. Setting it on the APP parent does nothing.
app_container.set_context(TenantId, TenantId("acme"))     # ignored for REQUEST-scoped providers
request_container = app_container.build_child_container(scope=Scope.REQUEST)
```

Fix: set the value on the container whose scope matches the provider's scope:

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

`ContextProvider(scope=Scope.APP, context_type=TenantId)` looks up the value on the APP container. If you `set_context` on the REQUEST child container, the APP-scope provider doesn't see it.

Fix: match the scope. If the value is per-request, declare `ContextProvider(scope=Scope.REQUEST, ...)` and `set_context` on the request container (or pass via `build_child_container(context=...)`).

### 3. Framework integration didn't inject the expected request

Framework integrations (`modern-di-fastapi`, `modern-di-litestar`) register the per-request `Request`/`WebSocket` automatically. If your code expects, say, `fastapi.Request` but you're outside the framework's request lifecycle (a background task, a CLI command), no `Request` is in context and the lookup fails.

Fix: only depend on framework-injected context inside the framework's request handling. For background tasks, build the REQUEST child container yourself and pass the necessary context.

## See also

- [Context Provider](../providers/context.md) — the full `ContextProvider` and `set_context` API.
- [Scopes](../providers/scopes.md) — per-container context registries, why context never propagates between containers.
- [Async resources via lifespan](../recipes/async-lifespan.md) — the canonical "construct in lifespan, inject as context" pattern.
