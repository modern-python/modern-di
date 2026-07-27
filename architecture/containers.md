# Containers

`Container` is the central entry point for the dependency injection system. Every interaction with
providers — resolution, scoping, overriding — flows through a `Container`.

## Creating a root container

```python
from modern_di import Container, Scope, Group


class MyGroup(Group): ...


container = Container(scope=Scope.APP, groups=[MyGroup])
```

Constructor parameters:

| Parameter | Default | Effect |
|---|---|---|
| `scope` | `Scope.APP` | The scope level this container occupies. Must be an `IntEnum`. |
| `groups` | `None` | One or more `Group` subclasses whose providers are registered into `providers_registry`. |
| `context` | `None` | Mapping of `type → object` pre-populated into `context_registry`. |
| `use_lock` | `True` | Wraps resolution in a `threading.RLock`; set `False` for single-threaded use. |
| `validate` | `None` | Deprecated and ignored — see below. |

A root container (no `parent_container`) creates fresh `ProvidersRegistry` and `OverridesRegistry`
instances. It also auto-registers `container_provider` (see [below](#container_provider)) under the
`Container` type.

A freshly-constructed container starts **open** (`closed = False`) — see
[Optional-open lifecycle](#optional-open-lifecycle).

### `validate` (deprecated constructor argument)

`validate: bool | None = None` no longer gates anything. Passing `True` or `False` emits
`exceptions.ValidateArgumentWarning` (a `DeprecationWarning`) and changes nothing about the container
built; omitting the argument (its default, `None`) is silent. The check it used to gate is entirely
explicit now: call [`container.validate()`](#validate) whenever you want the graph checked — see
[validation.md](validation.md) for what that check does. `validate` is removed in 4.0.

## Optional-open lifecycle

A container is **open** the moment it is constructed (`closed = False`) — there is no required
`open()` step and no first-use preparation. `close_sync()` / `close_async()` run finalizers and set
`closed = True`; that is the only way a container becomes closed. `open()` and `with` / `async with`
stay available — call them to get finalizers on the way out, and to reopen a closed container
deliberately:

```python
container = Container(scope=Scope.APP, groups=[MyGroup])
container.resolve(...)  # closed=False from construction -> resolves directly

# finalizers on the way out:
with Container(scope=Scope.APP, groups=[MyGroup]) as container:
    container.resolve(...)
# exit closes it; re-entering (or an implicit resolve) reopens it
```

Two states, tracked by the public `closed: bool`:

| State | `closed` | Implicit use | `open()` / `with` |
|---|---|---|---|
| Open | `False` | proceeds | no-op |
| Closed | `True` | reopens, warns | reopens, silent |

Reusing a closed container **implicitly** — a `resolve` / `resolve_provider` / `resolve_dependency`
that reaches it without going through `open()` / `with` first, directly or by building a child and
resolving through it — reopens it and emits `ContainerClosedWarning` (a `RuntimeWarning`, so it is
visible outside `__main__`, unlike `DeprecationWarning`); calling `open()` explicitly reopens silently,
since a deliberate reopen is not a diagnostic-worthy event. The warning is per container, not per
resolve: a closed REQUEST child resolving an APP-scoped provider through a closed APP parent reopens
and warns twice, once for each closed container the resolve passes through. See [Lifecycle: close and
reopen](#lifecycle-close-and-reopen) for what close and reopen do to the cache, and [Open and
reopen](#open-and-reopen-context-manager-protocol) for `_prepare()` / `open()` mechanics.

## Child containers

```python
with container.build_child_container(scope=Scope.REQUEST, context={MyRequest: request_obj}) as child:
    child.resolve(...)
```

`build_child_container` creates a new `Container` whose `parent_container` is the current one.
Rules:

- The child's scope must be strictly greater (deeper) than the parent's scope; `Container.__init__` is the
  guard, so passing a too-shallow scope to `build_child_container` raises `InvalidChildScopeError` from there.
  Passing `scope=None` derives the next scope via `scope._next_deeper` — the shallowest *member* deeper than
  the parent, **not** `value + 1`, so non-contiguous custom enums (`TENANT=6, JOB=10`) work; if the parent is
  already at the deepest member, `MaxScopeReachedError` is raised. See
  [scopes.md](scopes.md#the-scope-algebra).
- Building a child does not require the parent be open. `build_child_container` reads the parent's
  `_scope_map` and its two shared registries (`providers_registry`, `overrides_registry`); it resolves
  nothing and touches no cache, so a closed parent is irrelevant to it — there is no closed-check on
  the parent. The returned child itself starts open, same as any freshly-constructed container; see
  [Optional-open lifecycle](#optional-open-lifecycle).

  This is safe because validation state lives on the shared `ProvidersRegistry`, not on any one
  container, and nothing validates automatically in the first place — `validate()` is the only trigger
  (see [validation.md](validation.md)). Building a child off a closed parent therefore skips nothing
  that would otherwise have run.

The child gets its own, independent `_scope_map` dict holding all of its ancestors, enabling
`find_container(scope)` to reach any ancestor scope in O(1). The map never contains the container
itself: a `scope: self` entry would make every container a reference cycle, so no container could
be freed by reference counting and each would wait for a generational GC pass. `find_container`
short-circuits on its own scope before consulting the map, so the self-entry was never read.

## Registry sharing

The four registries split into two categories:

| Registry | Shared across container tree? | Purpose |
|---|---|---|
| `ProvidersRegistry` | Yes — all containers share one instance | Maps `type → AbstractProvider`; populated at root construction time from `groups`, and later via `Container.add_providers`. Also holds the shared `_plans` wiring-plan memo (keyed by `provider_id`, cleared on registry mutation), so a plan is built once tree-wide. |
| `OverridesRegistry` | Yes — all containers share one instance | Maps `provider_id → override object`; used by tests to substitute real instances. |
| `CacheRegistry` | No — each container has its own | Maps `provider_id → CacheItem`; stores resolved singleton instances and their finalizers for this scope level. |
| `ContextRegistry` | No — each container has its own | Maps `type → runtime object`; populated via `context=` at construction or `container.set_context()` after the fact. |

Because `ProvidersRegistry` and `OverridesRegistry` are shared, registering a group or setting an
override on any container in the tree is immediately visible to all other containers in the same
tree.

### Integration seam

`add_providers` (registration) and `resolve_dependency` (provider-or-type
dispatch) are the blessed integration seam — see
[writing-integrations.md](../docs/integrations/writing-integrations.md).
`add_providers` is **root-only**: called on a child, it raises
`ChildContainerRegistrationError` (`modern_di/exceptions.py`), since the
registry it mutates is shared tree-wide. All validation state lives on the
shared `ProvidersRegistry`, not on `Container` — there is no per-container
validated flag (see [validation.md](validation.md#what-validate-checks)).
`add_providers` registers and nothing more: it does not validate, and there
is no rollback on a bad batch — a cycle or inverted scope introduced by the
new providers is only reported the next time something calls
[`validate()`](#validate). The one effect on validation state is indirect:
mutating the registry clears `ProvidersRegistry._validated`, so a later
`validate()` re-walks the now-larger graph rather than trusting a stale clean
result. Because the registry is shared tree-wide, a batch registered through
the root is immediately visible to every container in the tree, so a child's
`resolve` sees a root's `add_providers` call without the child doing anything.
`resolve_dependency` carries no restriction of its own; it is a resolve verb,
callable on any container regardless of validation state.

## `container_provider`

A singleton instance of `_ContainerProvider` is registered under the `Container` type in the
`ProvidersRegistry` of every root container. Its `resolve` method returns the container passed to
it, so resolving `Container` from any child yields that child container — not the root; see
[docs/providers/container.md](../docs/providers/container.md) for the user-facing behavior and
examples. `_ContainerProvider` has `scope=Scope.APP` and `bound_type=None` (it is registered
explicitly under `Container` rather than inferred from a type annotation).

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

2. **`closed = True`** — set in a `finally` block, even if finalizers raised. A subsequent
   `resolve_provider` (or a nested provider resolving at a closed ancestor scope) self-heals: it
   reopens the container via `_prepare()` and emits `ContainerClosedWarning`, rather than raising.
   Re-enter the container via `with`/`async with`, or call `container.open()`, for a silent reopen
   instead — see [Optional-open lifecycle](#optional-open-lifecycle).

Additionally, when `close_sync()` or `close_async()` is called on a **root** container (one with
no `parent_container`), all overrides are cleared from the shared `OverridesRegistry` before the
cache is finalized.

Child containers only finalize their own `CacheRegistry`; the shared `OverridesRegistry` is left
alone.

### `clear_cache` per `CacheItem`

After running a finalizer, `CacheItem._clear()` evicts the cached instance (and resets `finalized`)
only if `CacheSettings.clear_cache` is `True` (the default); otherwise the cached value survives
close, ready to be returned again without re-running the creator.

### Open and reopen (context-manager protocol)

`_prepare()` — not `open()` — is the primitive the resolve path calls: `resolve_provider` (and the
compiled-resolver dispatch it wraps) calls it whenever `self.closed` is `True`, before doing anything
else. Under the container's `_lock` it re-checks `closed` (another thread may have reopened the
container already); if still closed, it warns with `ContainerClosedWarning` and clears `closed`. `open()`
is a separate, public entry point that clears `closed` unconditionally, with no closed-check and no
warning — a deliberate reopen is not a diagnostic-worthy event. Neither method runs validation; `open()`
is a plain lifecycle op, symmetric with `close_sync()` / `close_async()`. `Container` implements both
sync (`__enter__` / `__exit__`) and async (`__aenter__` / `__aexit__`) context managers; both call
`open()` on entry and `close_sync()` / `close_async()` on exit.

Concretely: using the same container object as a context manager a second time reopens it (clears
`closed`), resolves providers fresh if `clear_cache=True` was set on their `CacheSettings` (since
close removed those cached values), and then closes it again on exit. Providers whose
`CacheSettings.clear_cache` is `False` retain their cached instances across reopen cycles.

`open()` is optional — see [Optional-open lifecycle](#optional-open-lifecycle) — but prefer the `with`
form, or an explicit `open()` call, over relying on implicit reuse: both avoid `ContainerClosedWarning`
and put the reopen at a well-defined point instead of the first request. `open()` is exposed as a
public method for callback-style lifecycles that cannot wrap the container in a `with` block — for
example a framework startup hook that reopens a long-lived root container after a shutdown. The
FastStream integration uses exactly this: `app.on_startup(container.open)` paired with
`app.after_shutdown(container.close_async)`.

## `validate()`

See [validation.md](validation.md) for what `container.validate()` checks and how it reports
aggregated errors. It is the only thing that validates — construction, `open()`, and `add_providers`
never do.

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
