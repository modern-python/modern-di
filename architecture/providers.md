# Provider Catalog

This document describes every provider type in `modern-di`. It is the authoritative reference; if anything here
conflicts with other documentation, the code governs.

---

## `Group` — provider namespace

`Group` is a non-instantiable base class. Attempting to instantiate it (or any subclass) raises
`GroupInstantiationError`. Its sole purpose is to act as a namespace for declaring providers as class-level
attributes:

```python
from modern_di import providers, Group, Scope

class AppProviders(Group):
    db_pool = providers.Factory(scope=Scope.APP, creator=create_pool)
    user_repo = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)
```

`Group.get_providers()` walks the MRO and collects every class attribute that is an `AbstractProvider` instance,
respecting inheritance order and de-duplicating by name.

---

## `Factory` — the universal provider

`Factory` is the main building block. Every provider that calls a creator callable (a constructor or factory function passed as `creator=`) is a `Factory`.

### Signature

```python
Factory(
    *,
    scope: IntEnum = Scope.APP,
    creator: Callable[..., T],
    bound_type: type | None = UNSET,
    kwargs: dict[str, Any] | None = None,
    cache_settings: CacheSettings[T] | None = None,
    skip_creator_parsing: bool = False,
)
```

### Declaration-time signature parsing

When `skip_creator_parsing=False` (the default), `Factory.__init__` calls `types_parser.parse_creator(creator)`
immediately. This extracts the return type (used as the provider's `bound_type` unless overridden) and a mapping
of parameter names to `SignatureItem` descriptors. Dependency resolution is therefore type-driven: at resolution
time each parameter is matched against the container's `providers_registry` by its annotated type.

If `bound_type` is supplied explicitly it overrides the inferred return type (useful when the creator returns a
protocol or base class narrower than the concrete type).

A creator parameter that cannot be resolved by type raises `UnsupportedCreatorParameterError` at **declaration
time**. This fires when a parameter is a parameterized generic (e.g. `list[int]`, `dict[str, Foo]`) or
positional-only, has no default, and is not supplied via `kwargs`. The three escape hatches are: pass the value
via `kwargs={...}`, give the parameter a default, or set `skip_creator_parsing=True`.

### Recursive resolution

When a `Factory` is resolved, `WiringPlan.build` (in `modern_di/wiring.py`) iterates the parsed parameter map and
partitions it into the plan; `Factory` then recurses into `container.resolve_provider(dep_provider)` for each matched
provider. The plan is built once and memoized on the `CacheItem`. Resolution errors are annotated with a breadcrumb
describing the current factory, so the full chain appears in the exception.

### Static kwargs

Pass `kwargs` to supply static (non-DI-resolved) arguments that bypass type-based resolution — for
example `kwargs={"timeout": 30}` to pin a creator's `timeout` parameter. These are merged
last, overriding any provider-resolved value for the same key. Supplying a key that does not appear in the
creator's signature (and whose creator has no `**kwargs`) raises `UnknownFactoryKwargError` at declaration time.

### `skip_creator_parsing=True`

Disables signature introspection entirely — useful for callables whose signatures cannot be reflected (built-in C
extensions, `functools.partial`, etc.). When set without an explicit `bound_type`, a `UserWarning` is emitted
because the provider cannot be resolved by type.

---

## `CacheSettings` — singleton behavior

There is **no separate `Singleton` class**. Singleton behavior is opted into by passing a `CacheSettings` instance
to `Factory(cache_settings=...)`:

```python
providers.Factory(scope=Scope.APP, creator=Database, cache_settings=providers.CacheSettings())
```

`CacheSettings` is a `dataclass` with the following fields:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `clear_cache` | `bool` | `True` | Whether the cached instance is evicted when the container closes. |
| `finalizer` | `Callable[[T], None \| Awaitable[None]] \| None` | `None` | Optional teardown called on container close, before cache eviction. |
| `is_async_finalizer` | `bool` | *(computed)* | Set automatically in `__post_init__`; `True` when `finalizer` is a coroutine function. |

`is_async_finalizer` is not an init parameter — it is derived by `inspect.iscoroutinefunction(finalizer)` in
`__post_init__`. The container uses it to decide whether to `await` the finalizer.

Without `cache_settings`, `Factory.resolve` calls the creator on every resolution and returns a fresh instance
each time.

---

## `ContextProvider` — runtime-injected values

`ContextProvider` holds a value that is supplied at container-creation time via the `context` mapping rather than
being constructed by a factory:

```python
providers.ContextProvider(scope=Scope.REQUEST, context_type=HttpRequest)
```

At resolution time it looks the value up in the container's `context_registry` for the matching scope. If no
value was supplied (the key is absent), `resolve` returns `None`. `Factory._resolve_context_value` handles the
absent-context case live via the shared `absent_disposition` helper: if the dependent parameter has a default or is
nullable it is silently satisfied; otherwise an `ArgumentResolutionError` is raised.

`ContextProvider` also accepts an optional `bound_type` that overrides the inferred bound type.

---

## `Alias` — re-exporting a type under a different name

`Alias` delegates resolution to another registered provider, located by the source type:

```python
providers.Alias(source_type=ConcreteDatabase, bound_type=DatabaseProtocol)
```

This lets code that depends on `DatabaseProtocol` receive the `ConcreteDatabase` instance without the registry
needing a separate `Factory` for the protocol. `Alias.resolve` calls `container.resolve_provider(source_provider)`,
so caching and lifecycle are fully governed by the source.

`Alias` also accepts an optional `bound_type` that overrides the inferred bound type.

`Alias.effective_scope` follows alias chains transitively to the terminal non-alias provider and returns that
provider's scope. This is what `Container.validate()` and scope-error reporting use — the alias's own `scope`
attribute is only a stored default.

### Deprecated `scope=` parameter

Passing `scope=` to `Alias.__init__` emits a `DeprecationWarning`:

> "The `scope` parameter of Alias is deprecated and ignored: an alias's effective scope is derived from its
> source. It will be removed in a future release."

The parameter is accepted for backwards compatibility but has no effect on resolution. It will be removed in a
future release.

---

## `container_provider` — the container itself

`container_provider` is a pre-built singleton exported from `modern_di.providers`. It is automatically registered
in every container and resolves to the `Container` instance at the appropriate scope. Use it when a class needs to
accept the container as a dependency.

---

## Public exports

All provider types and `CacheSettings` are re-exported from `modern_di.providers`:

```python
from modern_di import providers

providers.Factory
providers.CacheSettings
providers.ContextProvider
providers.Alias
providers.AbstractProvider
providers.container_provider
```
