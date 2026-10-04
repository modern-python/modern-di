# Migration guide: upgrading to modern-di 4.x

This document describes the changes required to migrate from modern-di 3.x to modern-di 4.0.

## Key changes

### `Container` takes only `scope` positionally

Every `Container` argument after `scope` is keyword-only: `Container(Scope.APP, None)` raises
`TypeError`, so pass `parent_container=`, `context=` and `groups=` by name.

### `use_lock` is removed

`Container(use_lock=...)` raises `TypeError`; drop the argument. Every container tree is now
locked, and the lock is taken only on a cache miss (see
[Design decisions](../introduction/design-decisions.md#2-cached-factories-are-thread-safe)).

### Resolving on a closed container raises

In 3.x, resolving from a closed container, or through a child whose resolve reached a closed
ancestor, emitted `ContainerClosedWarning` and reopened it. In 4.0 the same call raises
`ContainerClosedError` and the container stays closed. `ContainerClosedWarning` is removed, so delete
any `filterwarnings` entry that names it. To use a closed container again, reopen it first with
`open()` or by re-entering `with` / `async with`, which calls `open()`. See
[Troubleshooting: ContainerClosedError](../troubleshooting/container-closed-error.md).

### Scope and closed-container errors are also `ResolutionError`s

`ScopeNotInitializedError`, `ScopeSkippedError` and `ContainerClosedError` now subclass
`ResolutionError` as well as `ContainerError`, so `except ResolutionError` catches every modern-di
error raised by `resolve()` and `resolve_provider()`. `except ContainerError` still catches them. If an
`except ResolutionError` clause comes before an `except ContainerError` clause, the first one now
handles these three errors; reorder the clauses if the `ContainerError` handler should run. See
[Errors and exceptions](../providers/errors-and-exceptions.md).

### Context values are required unless the provider sets `default=`

In 3.x, when a `Factory` parameter was backed by a `ContextProvider` and no context value was set,
the parameter decided what happened: a creator default was used, a nullable `X | None` parameter got
`None`, and only a required parameter raised `ArgumentResolutionError`. In 4.0 a `ContextProvider` is
an ordinary dependency. With no value set it raises `ContextValueNotSetError`, whether it is
resolved directly or as a `Factory` argument, and the parameter's default and annotation are
ignored. For a `Factory` argument, the message and `.parameter_name` name the parameter.

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

### Exception attributes are renamed

`ArgumentResolutionError` names the creator parameter the same way the other errors do:

- `.arg_name` is now `.parameter_name`, and `.arg_type` is now `.parameter_type`. The constructor
  keywords are renamed to match.
- `.bound_type` holds only the provider's bound type, and is `None` when the provider has none. In
  3.x it held the creator in that case; read `.creator` for it now.
- `.member_types` is stored: the union members when the parameter has no single type.

`ContextValueNotSetError` stores `.provider_scope`, the provider's scope as an `IntEnum`, and
`.parameter_name`. Neither attribute existed in 3.x, so code that only catches the error or reads
`.context_type` is unaffected. Code that constructs it must pass `provider_scope=Scope.APP` (or
another member) in place of the 3.x `scope_name="APP"` string.

`modern_di.exceptions` no longer re-exports `DependencyPathMixin` or `SUGGESTION_HEADER`. Neither
was meant for use outside the package. Import them from `modern_di.exceptions.base` and
`modern_di.exceptions.rendering` if you still need them.

### `FinalizerError` is an `ExceptionGroup`

`FinalizerError` now subclasses `ExceptionGroup` as well as `ModernDIError`, so `except*` can catch
the finalizer errors inside it by type, `AsyncFinalizerInSyncCloseError` included.

- `.finalizer_errors` is removed. Read `.exceptions`, which is a tuple where `.finalizer_errors`
  was a list.
- `.is_async` is unchanged, and a group that `except*` splits off keeps it.
- `except FinalizerError` and `except ModernDIError` still catch it, and its message is unchanged.

```python
# 3.x
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    errors = exc.finalizer_errors

# 4.0
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    errors = exc.exceptions

# 4.0, by type
try:
    container.close_sync()
except* exceptions.AsyncFinalizerInSyncCloseError:
    ...
```

### The 3.x deprecations are removed

- `Container(validate=...)` raises `TypeError`, and `ValidateArgumentWarning` is gone with it. Drop
  the argument and call `container.validate()` where you want the graph checked.
- `Container.scope_map` and `Container.lock` are removed. Nothing replaces them as public API; call
  `find_container(scope)` to reach an ancestor.
- `ContextValueNoneWarning` and `UnvalidatedContainerWarning` are removed. Neither has been emitted
  since 3.0, so delete any `filterwarnings` entry or import that names them.
