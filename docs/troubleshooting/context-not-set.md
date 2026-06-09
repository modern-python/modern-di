# ContextProvider has no value

A `ContextProvider(context_type=SomeType)` resolves by looking up `SomeType` in the container's context registry. If no value was registered, the resolution fails (or returns `None`, depending on configuration).

## Understanding the error

```
RuntimeError: ContextProvider for <class 'TenantId'> has no value in container at scope REQUEST.
Call `container.set_context(TenantId, value)` before resolving, or pass it via
`build_child_container(context={TenantId: value})`.
```

The provider has nothing to resolve to because nothing was set for that type on this container.

## Common causes

### 1. `set_context` was called on the parent, after the child was built

Context does not propagate from parent to child after the fact. Each container has its own context registry.

```python
# ❌ Broken: child was built before set_context
request_container = app_container.build_child_container(scope=Scope.REQUEST)
app_container.set_context(TenantId, TenantId("acme"))     # invisible to request_container
```

Fix: set context **before** building the child, or pass the values in via `build_child_container`:

```python
# Option A: set on the parent first
app_container.set_context(TenantId, TenantId("acme"))
request_container = app_container.build_child_container(scope=Scope.REQUEST)

# Option B: pass directly to the child
request_container = app_container.build_child_container(
    scope=Scope.REQUEST,
    context={TenantId: TenantId("acme")},
)
```

### 2. The `ContextProvider`'s scope doesn't match where you set the context

`ContextProvider(scope=Scope.APP, context_type=TenantId)` looks up the value on the APP container. If you `set_context` on the REQUEST child container, the APP-scope provider doesn't see it.

Fix: match the scope. If the value is per-request, declare `ContextProvider(scope=Scope.REQUEST, ...)` and `set_context` on the request container (or pass via `build_child_container(context=...)`).

### 3. Framework integration didn't inject the expected request

Framework integrations (`modern-di-fastapi`, `modern-di-litestar`) register the per-request `Request`/`WebSocket` automatically. If your code expects, say, `fastapi.Request` but you're outside the framework's request lifecycle (a background task, a CLI command), no `Request` is in context and the lookup fails.

Fix: only depend on framework-injected context inside the framework's request handling. For background tasks, build the REQUEST child container yourself and pass the necessary context.

## See also

- [Context Provider](../providers/context.md) — the full `ContextProvider` and `set_context` API.
- [Scopes](../providers/scopes.md) — per-container context registries, why propagation is one-shot.
- [Async resources via lifespan](../recipes/async-lifespan.md) — the canonical "construct in lifespan, inject as context" pattern.
