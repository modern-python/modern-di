# Advanced / low-level API

Lower-level public surface for library authors and advanced use-cases.

## Supported extension points

### `Group.get_providers()`

`Group.get_providers()` is a classmethod that traverses the MRO (excluding `Group` and
`object`) and collects every class attribute that is an `AbstractProvider` instance, respecting
MRO override order (subclass attribute shadows parent attribute of the same name). Use it to
inspect or iterate all providers declared on a group hierarchy.

!!! note "The provider set is closed — `AbstractProvider` is not an extension point"
    `Factory`, `Alias`, `ContextProvider`, and the pre-built `container_provider` are the
    only provider types. `AbstractProvider` is their shared base and the type that appears
    in public signatures (`resolve_dependency`, `kwargs=`), but it is **not** a hook for
    adding your own: resolution compiles one closure per known provider type, so a subclass
    of `AbstractProvider` — or of `Factory` — raises `TypeError` at its first resolve, and
    `validate()` does not catch it. Compose behavior in a creator function, or use `Alias`,
    instead of introducing a provider type.

### `CacheSettings.is_async_finalizer`

`CacheSettings.is_async_finalizer` is a computed bool field set at construction time via
`inspect.iscoroutinefunction(finalizer)`. The cache registry uses it to decide whether to
`await` the finalizer during `close_async()` or treat it as sync.

### `find_container(scope)`

`find_container(scope)` walks `_scope_map` and returns the container registered at
`scope`; raises `ScopeNotInitializedError` or `ScopeSkippedError` if the scope is absent.
It is the primitive the compiled resolvers use to locate the container at a provider's
scope when it differs from the resolving container's.

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
  `use_lock=False`. A cached `Factory`'s compiled resolver hands it to `CacheItem.get_or_create`,
  which gates the cold-miss build so one instance is created per cache key.

The former public names `scope_map` and `lock` remain as read-only properties that emit
`DeprecationWarning` and will be removed in a future release.
