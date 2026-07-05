# Advanced / low-level API

Lower-level public surface for library authors and advanced use-cases.

## Supported extension points

### `Group.get_providers()`

`Group.get_providers()` is a classmethod that traverses the MRO (excluding `Group` and
`object`) and collects every class attribute that is an `AbstractProvider` instance, respecting
MRO override order (subclass attribute shadows parent attribute of the same name). Use it to
inspect or iterate all providers declared on a group hierarchy.

### Subclassing `AbstractProvider`

To implement a custom provider, subclass `AbstractProvider` and implement:

- **`resolve(container)`** *(required)* — returns the resolved instance.
- **`get_dependencies(container)`** *(optional)* — returns a `dict[str, AbstractProvider]`
  mapping parameter names to their providers; used by `Container.validate()` for graph
  traversal.
- **`iter_validation_issues(container)`** *(optional)* — yields `Exception` instances for
  validation-time problems found in this provider; default yields nothing.
- **`effective_scope(container)`** *(optional override)* — override this method to report the
  scope of whatever the provider ultimately resolves to. A transparent or redirect provider (like
  `Alias`) should override it to follow the source chain so that `Container.validate()` checks
  callers against the real target scope rather than any nominal scope on the wrapper itself.

### `CacheSettings.is_async_finalizer`

`CacheSettings.is_async_finalizer` is a computed bool field set at construction time via
`inspect.iscoroutinefunction(finalizer)`. `Factory.resolve` and the cache registry use it to
decide whether to `await` the finalizer during `close_async()` or treat it as sync.

### Deprecated: `cache_settings=`

`Factory(cache_settings=...)` is a deprecated alias of `cache=`. It still works but
emits a `DeprecationWarning`; pass `cache=True` (defaults) or `cache=CacheSettings(...)`
(tuned) instead. Passing both `cache` and `cache_settings` raises `TypeError`.

### `find_container(scope)`

`find_container(scope)` walks `_scope_map` and returns the container registered at
`scope`; raises `ScopeNotInitializedError` or `ScopeSkippedError` if the scope is absent.
It is the primitive a custom `AbstractProvider.resolve` calls to locate the container at
its scope — see [Subclassing `AbstractProvider`](#subclassing-abstractprovider) above.

## Container internals — no stability guarantee

!!! warning "Internal surface"
    These attributes back the container's own machinery. They are documented
    for debugging and deep integration work only, and may change without a
    deprecation cycle. Do not build on them.

- **`parent_container`** — constructor kwarg and slot; the direct parent of a child container,
  or `None` for a root. Passing a `scope ≤ parent.scope` raises `InvalidChildScopeError`.
- **`_scope_map`** — `dict[IntEnum, Container]` mapping every scope in the chain to its
  container; built at construction time and inherited (plus the new scope) by each child.
- **`_lock`** — a `threading.RLock` instance, or `None` when the container was created with
  `use_lock=False`. The lock gates singleton creation inside `Factory.resolve`.

The former public names `scope_map` and `lock` remain as read-only properties that emit
`DeprecationWarning` and will be removed in a future release.
