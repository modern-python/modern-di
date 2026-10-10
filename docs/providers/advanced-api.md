# Advanced / low-level API

Lower-level public surface for library authors and advanced use-cases.

## What is public

Import public names from four modules, and only from them:

- `modern_di`: `Container`, `Group`, `Scope`, `OverrideHandle` (what `override()` returns),
  `Suggestion` (an element of an error's `.suggestions`), `UNSET` and its type `UnsetType`, plus
  the three submodules below.
- `modern_di.providers`: the provider types, `CacheSettings` and `container_provider`.
- `modern_di.exceptions`: every error class.
- `modern_di.integrations`: the building blocks for framework integrations.

Every other module is internal and can change in any release, even one that defines an exported
name. That covers `modern_di.container`, `modern_di.group`, `modern_di.scope`, `modern_di.types`,
`modern_di.suggester`, the `modern_di.registries` and `modern_di.providers` submodules, and the
rest. Names that start with an underscore are internal wherever they are.

## Supported extension points

### `Group.get_providers()`

`Group.get_providers()` is a classmethod that traverses the MRO (excluding `Group` and
`object`) and collects every class attribute that is an `AbstractProvider` instance, respecting
MRO override order (subclass attribute shadows parent attribute of the same name). Use it to
inspect or iterate all providers declared on a group hierarchy. `Group.get_named_providers()`
returns the same providers as a dict keyed by attribute name.

!!! note "The provider set is closed: `AbstractProvider` is not an extension point"
    `Factory`, `Alias`, `ContextProvider`, and the pre-built `container_provider` are the
    only provider types. `AbstractProvider` is their shared base and the type that appears
    in public signatures (`resolve_dependency`, `kwargs=`), but it is not a hook for
    adding your own: resolution compiles a resolver per known provider type, so defining a
    subclass of `AbstractProvider` (or of `Factory`) raises `TypeError` when the class is
    created. Compose behavior in a creator function, or use `Alias`, instead of introducing a
    provider type.

## Container navigation

- `parent_container` is a read-only property: the container a child was built from, or `None` for a
  root. `scope` is read-only too. `Container(...)` builds a root; children come only from
  `build_child_container()`, which raises `InvalidChildScopeError` for a `scope` that is not deeper.
- `build_child_container()` on a `Container` subclass returns an instance of that subclass. It does
  not call the subclass's `__init__`, so state that `__init__` sets exists on the root only.
- `find_container(scope)` returns `self` when `scope` is the container's own scope, otherwise the
  ancestor container at that scope, and raises `ScopeNotInitializedError` or `ScopeSkippedError`
  when no ancestor has it. Each container records its ancestors by scope when it is built, and the
  compiled resolvers read that record directly on every cross-scope hop. They call
  `find_container` only when the scope is missing from it, so overriding `find_container` in a
  `Container` subclass does not redirect navigation. `resolve` and `resolve_provider` are entry
  points, not hooks either: a compiled resolver calls its dependencies' resolvers directly, so an
  override of either sees only the top-level call.
- Each cached `Factory` gets its own `threading.RLock` in each container that caches it, created
  with the cache item on the first resolve there. Building a child allocates no lock. On a cold
  cache miss the factory holds its lock while it resolves its dependencies and calls the creator,
  so one instance is created per cache key. A warm resolve does not take the lock.
