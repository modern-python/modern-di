# Advanced / low-level API

Lower-level public surface for library authors and advanced use-cases.

## Supported extension points

### `Group.get_providers()`

`Group.get_providers()` is a classmethod that traverses the MRO (excluding `Group` and
`object`) and collects every class attribute that is an `AbstractProvider` instance, respecting
MRO override order (subclass attribute shadows parent attribute of the same name). Use it to
inspect or iterate all providers declared on a group hierarchy.

!!! note "The provider set is closed: `AbstractProvider` is not an extension point"
    `Factory`, `Alias`, `ContextProvider`, and the pre-built `container_provider` are the
    only provider types. `AbstractProvider` is their shared base and the type that appears
    in public signatures (`resolve_dependency`, `kwargs=`), but it is not a hook for
    adding your own: resolution compiles a resolver per known provider type, so a subclass
    of `AbstractProvider` (or of `Factory`) raises `TypeError` at its first resolve, and
    `validate()` does not catch it. Compose behavior in a creator function, or use `Alias`,
    instead of introducing a provider type.

### `CacheSettings.is_async_finalizer`

`CacheSettings.is_async_finalizer` is a computed bool field set at construction time via
`inspect.iscoroutinefunction(finalizer)`. The cache registry uses it to decide whether to
`await` the finalizer during `close_async()` or treat it as sync.

## Container internals: no stability guarantee

!!! warning "Internal surface"
    These attributes back the container's own machinery. They are documented
    for debugging and deep integration work only, and may change without a
    deprecation cycle. Do not build on them.

- `parent_container` is a constructor kwarg and slot: the direct parent of a child container,
  or `None` for a root. Passing a `scope ≤ parent.scope` raises `InvalidChildScopeError`.
- `_scope_map` is a `dict[IntEnum, Container]` mapping each **ancestor's** scope to its
  container, built at construction time, with a child inheriting its parent's map plus the parent
  itself. A root's map is empty. The container is never in its own map, since that self-reference
  would make every container a reference cycle, and `find_container` never needs it: it
  short-circuits on its own scope first. The compiled resolvers read it directly on every
  cross-scope hop.
- `find_container(scope)` returns `self` when `scope` is the container's own scope, otherwise
  the ancestor in `_scope_map`, and raises `ScopeNotInitializedError` or `ScopeSkippedError` when
  the scope is absent. The compiled resolvers call it only on that miss, so overriding it in a
  `Container` subclass does not redirect navigation. `resolve` and `resolve_provider` are entry
  points, not hooks either: a compiled resolver calls its dependencies' resolvers directly, so an
  override of either sees only the top-level call.
- `_lock` is the tree's `threading.RLock`, created by the root and shared by every child, or
  `None` when the root was created with `use_lock=False`. A cached `Factory`'s compiled resolver
  hands it to `CacheItem.get_or_create`, which gates the cold-miss build so one instance is created
  per cache key.

The former public names `scope_map` and `lock` remain as read-only properties that emit
`DeprecationWarning` and will be removed in a future release.
