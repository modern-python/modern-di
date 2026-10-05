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

## Container navigation

- `parent_container` is a constructor kwarg: the direct parent of a child container, or `None` for
  a root. Passing a `scope ≤ parent.scope` raises `InvalidChildScopeError`.
- `find_container(scope)` returns `self` when `scope` is the container's own scope, otherwise the
  ancestor container at that scope, and raises `ScopeNotInitializedError` or `ScopeSkippedError`
  when no ancestor has it. Each container records its ancestors by scope when it is built, and the
  compiled resolvers read that record directly on every cross-scope hop. They call
  `find_container` only when the scope is missing from it, so overriding `find_container` in a
  `Container` subclass does not redirect navigation. `resolve` and `resolve_provider` are entry
  points, not hooks either: a compiled resolver calls its dependencies' resolvers directly, so an
  override of either sees only the top-level call.
- Each cached `Factory` gets its own `threading.RLock` in each container that caches it, created
  with the cache slot on the first resolve there. Building a child allocates no lock. On a cold
  cache miss the factory holds its lock while it resolves its dependencies and calls the creator,
  so one instance is created per cache key. A warm resolve does not take the lock.
