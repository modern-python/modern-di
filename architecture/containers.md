# Containers

`Container` is the central entry point for the dependency injection system. Every interaction with
providers — resolution, scoping, overriding — flows through a `Container`.

## Creating a root container

```python
from modern_di import Container, Scope, Group

class MyGroup(Group):
    ...

container = Container(scope=Scope.APP, groups=[MyGroup])
```

Constructor parameters:

| Parameter | Default | Effect |
|---|---|---|
| `scope` | `Scope.APP` | The scope level this container occupies. Must be an `IntEnum`. |
| `groups` | `None` | One or more `Group` subclasses whose providers are registered into `providers_registry`. |
| `context` | `None` | Mapping of `type → object` pre-populated into `context_registry`. |
| `use_lock` | `True` | Wraps resolution in a `threading.RLock`; set `False` for single-threaded use. |
| `validate` | `False` | If `True`, runs cycle and scope-ordering checks immediately after construction. |

A root container (no `parent_container`) creates fresh `ProvidersRegistry` and `OverridesRegistry`
instances. It also auto-registers `container_provider` under the `Container` type so that any
provider declaring `Container` as a dependency receives the resolving container instance directly.

## Child containers

```python
child = container.build_child_container(scope=Scope.REQUEST, context={MyRequest: request_obj})
```

`build_child_container` creates a new `Container` whose `parent_container` is the current one.
Rules:

- The child's scope must be strictly greater (deeper) than the parent's scope. Passing `scope=None`
  auto-increments to the next `IntEnum` value; if the parent is already at the maximum scope,
  `MaxScopeReachedError` is raised.
- Building a child from a closed container raises `ContainerClosedError`.

The child gets its own, independent `scope_map` dict that includes all ancestors plus itself,
enabling `find_container(scope)` to walk up to any ancestor scope in O(1).

## Registry sharing

The four registries split into two categories:

| Registry | Shared across container tree? | Purpose |
|---|---|---|
| `ProvidersRegistry` | Yes — all containers share one instance | Maps `type → AbstractProvider`; populated once at root construction time from `groups`. |
| `OverridesRegistry` | Yes — all containers share one instance | Maps `provider_id → override object`; used by tests to substitute real instances. |
| `CacheRegistry` | No — each container has its own | Maps `provider_id → CacheItem`; stores resolved singleton instances and the memoized `WiringPlan` for this scope level. |
| `ContextRegistry` | No — each container has its own | Maps `type → runtime object`; populated via `context=` at construction or `container.set_context()` after the fact. |

Because `ProvidersRegistry` and `OverridesRegistry` are shared, registering a group or setting an
override on any container in the tree is immediately visible to all other containers in the same
tree.

## `container_provider`

A singleton instance of `_ContainerProvider` is registered under the `Container` type in the
`ProvidersRegistry` of every root container. Its `resolve` method returns the container passed to
it, so resolving `Container` from any child yields that child container — not the root. This lets
providers at any scope depth receive the container they are resolved from as a plain constructor
dependency.

`_ContainerProvider` has `scope=Scope.APP` and `bound_type=None` (it is registered explicitly
under `Container` rather than inferred from a type annotation).

## Lifecycle: close and reopen

The idiomatic happy path is the `with` statement: it builds the container, runs finalizers in
LIFO order on the way out, and guarantees close even if the body raises. Most code never needs to
call `close_sync()`/`close_async()` directly.

```python
with Container(scope=Scope.APP, groups=[MyGroup]) as container:
    ...  # resolve providers here; finalizers run on exit
```

The rest of this section documents what that close performs and how reopen works.

### Closing

`close_sync()` and `close_async()` both do two things in order:

1. **Finalizers** — iterate over the container's `CacheRegistry._creation_order` list in **reverse
   (LIFO)** order and call each `CacheItem`'s finalizer if one is configured and the item has not
   already been finalized. On `close_sync()`, any item whose finalizer is async raises
   `AsyncFinalizerInSyncCloseError`; those items are left in `_creation_order` so a subsequent
   `close_async()` can clean them up.

2. **`closed = True`** — always set in a `finally` block, even if finalizers raised. Subsequent
   calls to `build_child_container` or `resolve_provider` raise `ContainerClosedError`.

Additionally, when `close_sync()` or `close_async()` is called on a **root** container (one with
no `parent_container`), all overrides are cleared from the shared `OverridesRegistry` before the
cache is finalized.

Child containers only finalize their own `CacheRegistry`; the shared `OverridesRegistry` is left
alone.

### `clear_cache` per `CacheItem`

After running a finalizer, each `CacheItem` calls `_clear()`. This checks the item's
`CacheSettings.clear_cache` flag. If `True`, the cached instance is removed (`cache` is reset to
`UNSET`) and `finalized` is reset to `False`, leaving the slot ready to be re-populated on the
next resolution. If `False` (or no `CacheSettings`), the cached value is retained after
finalization; the item is simply marked finalized.

### Reopen (context-manager protocol)

`Container` implements both sync (`__enter__` / `__exit__`) and async (`__aenter__` / `__aexit__`)
context managers.

- `open()` sets `self.closed = False`. No other state is reset; `cache_registry` and
  `context_registry` are left as-is. Reopening an already-open container is a no-op.
- `__enter__` / `__aenter__` call `open()` and return `self`.
- `__exit__` calls `close_sync()`; `__aexit__` calls `close_async()`.

Concretely: using the same container object as a context manager a second time reopens it (clears
`closed`), resolves providers fresh if `clear_cache=True` was set on their `CacheSettings` (since
close removed those cached values), and then closes it again on exit. Providers whose
`CacheSettings.clear_cache` is `False` retain their cached instances across reopen cycles.

Prefer the `with` form. `open()` is exposed as a public method for callback-style lifecycles that
cannot wrap the container in a `with` block — for example a framework startup hook that must reopen
the long-lived root container before serving the next request. The FastStream integration uses
exactly this: `app.on_startup(container.open)` paired with `app.after_shutdown(container.close_async)`.

## `validate()`

`container.validate()` runs a depth-first traversal of all providers in `ProvidersRegistry`,
detecting circular dependencies and scope-ordering violations (a provider at a wider scope
depending on one at a narrower scope). Pass `validate=True` to the constructor to run this at
creation time, or call `container.validate()` explicitly at any point. It raises
`ValidationFailedError` with all collected errors if any are found.

## `set_context()`

```python
container.set_context(MyRequest, request_obj)
```

Registers a runtime value directly into the container's `ContextRegistry`. Context values are
resolved **live** on every resolve (see [resolution](resolution.md)), so a value set here is
picked up by subsequent resolves of **non-cached** providers — including factories in deeper-scoped
child containers that read this container's context — with no cache invalidation needed.

A **cached** provider (`Factory(cache=...)`) is built once and its instance is *not*
rebuilt by a later `set_context`; set the context before its first resolve.
