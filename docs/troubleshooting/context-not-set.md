# ContextProvider has no value

A `ContextProvider(SomeType)` resolves by looking up `SomeType` in the container's context registry. A context value is required: if none was registered and the provider declares no `default=`, resolving it raises `ContextValueNotSetError`, whether it is resolved directly or injected into a `Factory` parameter. A default or an `X | None` annotation on the parameter does not change that.

## Symptom

```
Cannot resolve dependency chain:
  REQUEST  MyService (myapp.ctx:9)
  caused by: No context value is set for <class 'myapp.ctx.TenantId'> (scope REQUEST), needed for argument tenant. Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider.
See: https://modern-di.modern-python.org/troubleshooting/context-not-set/
```

The top frame shows which provider failed, and the `caused by` line names the context type, the scope whose container was read, and the parameter it was needed for. A direct `container.resolve(TenantId)` raises the same error without the chain and without the `needed for argument` part. Inspect `.context_type` and `.arg_name` (`None` for a direct resolve).

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

If the provider has to resolve where no value is set, such as in a handler that also runs outside a request, give it a default. The provider returns `default=` whenever nothing is set:

```python
tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST, default=None)
```

When the provider belongs to an integration and should stay required, declare an app-owned optional provider for the same type instead; see [Optional context](../providers/context.md#optional-context-default).

## See also

- [Context providers](../providers/context.md) documents the full `ContextProvider` and `set_context` API.
- [Scopes](../providers/scopes.md) explains per-container context registries and why context never propagates between containers.
- [Async resources via lifespan](../recipes/async-lifespan.md) shows the canonical "construct in lifespan, inject as context" pattern.
