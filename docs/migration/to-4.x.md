# Migration guide: upgrading to modern-di 4.x

This document describes the changes required to migrate from modern-di 3.x to modern-di 4.0.

## Key changes

### `Container` takes only `scope` positionally

Every `Container` argument after `scope` is keyword-only: `Container(Scope.APP, None)` raises
`TypeError`, so pass `parent_container=`, `context=`, `groups=` and `use_lock=` by name.

### Resolving on a closed container raises

In 3.x, resolving from a closed container, or through a child whose resolve reached a closed
ancestor, emitted `ContainerClosedWarning` and reopened it. In 4.0 the same call raises
`ContainerClosedError` and the container stays closed. `ContainerClosedWarning` is removed, so delete
any `filterwarnings` entry that names it. To use a closed container again, reopen it first with
`open()` or by re-entering `with` / `async with`, which calls `open()`. See
[Troubleshooting: ContainerClosedError](../troubleshooting/container-closed-error.md).

### Context values are required unless the provider sets `default=`

In 3.x, when a `Factory` parameter was backed by a `ContextProvider` and no context value was set,
the parameter decided what happened: a creator default was used, a nullable `X | None` parameter got
`None`, and only a required parameter raised `ArgumentResolutionError`. In 4.0 a `ContextProvider` is
an ordinary dependency. With no value set it raises `ContextValueNotSetError`, whether it is
resolved directly or as a `Factory` argument, and the parameter's default and annotation are
ignored. For a `Factory` argument, the message and `.arg_name` name the parameter.

Optional context is declared once, on the provider: `ContextProvider(T, default=X)` returns `X`
whenever no value is set. If you own the provider, add `default=` to it:

```python
# 3.x: the creator default applied when no value was set
tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST)

# 4.0
tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST, default=None)
```

An integration's provider (`fastapi_request_provider`, `litestar_request_provider`, ...) stays
required. Suppose a factory's creator takes `request: fastapi.Request | None = None` and relies on
getting `None` outside a request, because FastStream consumers resolve it from the same container.
In 4.0 that resolve raises. Declare your own optional provider for the same type, keep it out of
type-based wiring with `bound_type=None`, and pass it explicitly. It reads the same context value
as the integration's provider:

```python
optional_request = providers.ContextProvider(
    fastapi.Request, scope=Scope.REQUEST, bound_type=None, default=None
)

dynamic_engine = providers.Factory(
    choose_sa_engine,
    scope=Scope.REQUEST,
    kwargs={
        "primary_engine": database_engine,
        "replica_engine": database_replica_engine,
        "request": optional_request,
    },
)
```

A parameter with a creator default and *no* provider registered for its type behaves as before:
the default applies. `ContextProvider.fetch_context_value()` is removed; resolve the provider
instead, giving it a `default=` if the value may be absent. See
[Context providers: optional context](../providers/context.md#optional-context-default).

### The 3.x deprecations are removed

- `Container(validate=...)` raises `TypeError`, and `ValidateArgumentWarning` is gone with it. Drop
  the argument and call `container.validate()` where you want the graph checked.
- `Container.scope_map` and `Container.lock` are removed. Nothing replaces them as public API; call
  `find_container(scope)` to reach an ancestor.
- `ContextValueNoneWarning` and `UnvalidatedContainerWarning` are removed. Neither has been emitted
  since 3.0, so delete any `filterwarnings` entry or import that names them.
