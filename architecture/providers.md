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

`Group.get_named_providers()` walks the MRO and returns a `dict[str, AbstractProvider]` mapping each declared
attribute name to its provider — respecting inheritance order, de-duplicating by first-seen name, and letting a
non-provider override mask the parent provider of the same name. `Group.get_providers()` is derived from it as
`list(cls.get_named_providers().values())`, so the traversal and de-duplication rules live in one place.

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
    cache: bool | CacheSettings[T] | None = None,
    cache_settings: CacheSettings[T] | None = UNSET,  # deprecated alias of `cache`
    skip_creator_parsing: bool = False,
)
```

### Declaration-time signature parsing

When `skip_creator_parsing=False` (the default), `Factory.__init__` calls `types_parser.parse_creator(creator)`
immediately. This extracts the return type (used as the provider's `bound_type` unless overridden) and a mapping
of parameter names to `SignatureItem` descriptors. Dependency resolution is therefore type-driven: at resolution
time each parameter is matched against the container's `providers_registry` by its annotated type.

If `bound_type` is supplied explicitly it overrides the inferred return type (useful when the creator returns a
protocol or base class narrower than the concrete type). See
[docs/providers/factories.md](../docs/providers/factories.md#creator-signature-support-matrix) for the full
per-parameter-shape behavior table (`UnsupportedCreatorParameterError` conditions, escape hatches, union
resolution order).

### Recursive resolution

When a `Factory` is resolved, `WiringPlan.build` (in `modern_di/wiring.py`) iterates the parsed parameter map and
partitions it into the plan; `Factory` then recurses into `container.resolve_provider(dep_provider)` for each matched
provider. The plan is memoized on the `CacheItem` and rebuilt when the providers-registry version has changed
(i.e. after `add_providers`). Resolution errors are annotated with a breadcrumb
describing the current factory, so the full chain appears in the exception.

### Static kwargs and `skip_creator_parsing`

See [docs/providers/factories.md](../docs/providers/factories.md#kwargs) for `kwargs=` (static values,
overriding provider-resolved ones for the same key; an unknown key raises `UnknownFactoryKwargError` at
declaration time, unless the creator accepts `**kwargs` or its signature cannot be reflected) and
`skip_creator_parsing=True` (disables signature introspection; a `UserWarning` is
emitted if `bound_type` isn't given explicitly, since the provider then can't be resolved by type).

---

## `CacheSettings` — singleton behavior

There is no separate `Singleton` class — see [docs/providers/factories.md](../docs/providers/factories.md)
for the user-facing singleton idiom and `cache_settings=`'s deprecation
([advanced-api.md#deprecated-cache_settings](../docs/providers/advanced-api.md#deprecated-cache_settings)).

`CacheSettings` is a `dataclass` with the following fields:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `clear_cache` | `bool` | `True` | Whether the cached instance is evicted when the container closes. |
| `finalizer` | `Callable[[T], None \| Awaitable[None]] \| None` | `None` | Optional teardown called on container close, before cache eviction. |
| `is_async_finalizer` | `bool` | *(computed)* | Not an init parameter — derived by `inspect.iscoroutinefunction(finalizer)` in `__post_init__`. The container uses it to decide whether to `await` the finalizer. |

Without `cache`, `Factory.resolve` calls the creator on every resolution and returns a fresh instance
each time.

---

## `ContextProvider` — runtime-injected values

`ContextProvider` holds a value that is supplied at container-creation time via the `context` mapping rather than
being constructed by a factory:

```python
providers.ContextProvider(scope=Scope.REQUEST, context_type=HttpRequest)
```

At resolution time it looks the value up in the container's `context_registry` for the matching scope. What
happens next depends on **how** the value is fetched — direct resolve vs. as another provider's dependency —
and the two paths are independent:

- **Direct resolve** (`container.resolve(HttpRequest)` / `container.resolve_provider(the_provider)` →
  `ContextProvider.resolve`): if no value was supplied (the key is absent), it emits
  `ContextValueNoneWarning` (a `DeprecationWarning` naming the context type and scope) and
  returns `None`. modern-di 3.0 raises `ContextValueNotSetError` here instead of warning —
  see the [migration guide](../docs/migration/to-3.x.md). Escalate the warning now to catch unset-context bugs
  ahead of the 3.0 upgrade: `warnings.filterwarnings("error", category=exceptions.ContextValueNoneWarning)`.
- **As a dependent parameter** of another provider (e.g. a `Factory` constructor argument typed as the context
  type): unchanged by the above — `Factory` reads the value via `fetch_context_value` (not `resolve`), so no
  warning fires on this path. `Factory._resolve_context_value` handles the absent-context case live via the
  shared `absent_disposition` helper: if the dependent parameter has a default or is nullable it is silently
  satisfied; otherwise an `ArgumentResolutionError` is raised, exactly as before this warning was added.

`ContextProvider` also accepts an optional `bound_type` that overrides the inferred bound type.

---

## `Alias` — re-exporting a type under a different name

`Alias` delegates resolution to another registered provider, located by the source type:

```python
providers.Alias(source_type=ConcreteDatabase, bound_type=DatabaseProtocol)
```

`Alias.resolve` calls `container.resolve_provider(source_provider)` — it holds no cache of its own — and also
accepts an optional `bound_type` override. See [docs/providers/alias.md](../docs/providers/alias.md) for the
user-facing rationale and caching implications.

`Alias.effective_scope` follows alias chains transitively to the terminal non-alias provider and returns that
provider's scope. This is what `Container.validate()` and scope-error reporting use — the alias's own `scope`
attribute is only a stored default.

### Deprecated `scope=` parameter

Passing `scope=` to `Alias.__init__` emits a `DeprecationWarning` and has no effect on resolution or validation
(both are derived from the source, per above) — see [docs/providers/alias.md](../docs/providers/alias.md) for
the user-facing note. The stored value is kept internally only so that cosmetic consumers (`__repr__`, registry
suggestions) continue to display it; it is scheduled for removal in a future release.

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
