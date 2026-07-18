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
| `validate` | `None` | Tri-state, see below. |

A root container (no `parent_container`) creates fresh `ProvidersRegistry` and `OverridesRegistry`
instances. It also auto-registers `container_provider` (see [below](#container_provider)) under the
`Container` type.

### `validate`'s three states

See [validation.md](validation.md) for what each state does and why. The container-specific wrinkle:
child containers built via `build_child_container` never pass `validate` explicitly, so they always
land on the unset (`None`) branch — but `UnvalidatedContainerWarning` additionally requires
`parent_container is None`, which is false for every child. So children never warn, regardless of
`validate`'s value.

Escalate the warning to catch it in CI ahead of the 3.0 upgrade:

```python
warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)
```

## Child containers

```python
child = container.build_child_container(scope=Scope.REQUEST, context={MyRequest: request_obj})
```

`build_child_container` creates a new `Container` whose `parent_container` is the current one.
Rules:

- The child's scope must be strictly greater (deeper) than the parent's scope; `Container.__init__` is the
  guard, so passing a too-shallow scope to `build_child_container` raises `InvalidChildScopeError` from there.
  Passing `scope=None` derives the next scope via `scope._next_deeper` — the shallowest *member* deeper than
  the parent, **not** `value + 1`, so non-contiguous custom enums (`TENANT=6, JOB=10`) work; if the parent is
  already at the deepest member, `MaxScopeReachedError` is raised. See
  [scopes.md](scopes.md#the-scope-algebra).
- Building a child from a closed container is transitional until modern-di 3.0: it emits
  `ContainerClosedWarning` and self-reopens the container instead of raising `ContainerClosedError`
  (see [Lifecycle: close and reopen](#lifecycle-close-and-reopen) below).

The child gets its own, independent `_scope_map` dict that includes all ancestors plus itself,
enabling `find_container(scope)` to walk up to any ancestor scope in O(1).

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
registry it mutates is shared tree-wide. `Container` tracks a private
`_validated` flag, set once `validate()` succeeds on **this** container
(construction or a manual call); it is the per-container gate for
`add_providers`, which on an already-validated container re-runs `validate()`
after registering and, if that fails, removes the just-added batch again —
the container ends up either fully registered and valid, or unchanged.
Whether the graph is *currently* validation-clean is tracked separately and
registry-level, by `ProvidersRegistry`'s `_validated` flag (see
[validation.md](validation.md#what-validate-checks)). Because that registry is
shared tree-wide, validating any container in the tree marks the whole graph
clean, so a child's `resolve` benefits from the root's validation — its runtime
cycle guard short-circuits — without the child ever calling `validate()` itself.
`resolve_dependency` carries no such restriction; it is a resolve verb,
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

2. **`closed = True`** — always set in a `finally` block, even if finalizers raised. Until modern-di
   3.0, a subsequent `resolve_provider` / `build_child_container` (or a nested provider resolving at
   a closed ancestor scope) emits a `ContainerClosedWarning` and **self-reopens** the container, then
   proceeds — preserving pre-2.16 "close then resolve" code. Escalate the warning
   (`warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)`) to opt into the
   strict behavior early. In 3.0 these paths raise `ContainerClosedError` instead.

Additionally, when `close_sync()` or `close_async()` is called on a **root** container (one with
no `parent_container`), all overrides are cleared from the shared `OverridesRegistry` before the
cache is finalized.

Child containers only finalize their own `CacheRegistry`; the shared `OverridesRegistry` is left
alone.

### `clear_cache` per `CacheItem`

After running a finalizer, `CacheItem._clear()` evicts the cached instance (and resets `finalized`)
only if `CacheSettings.clear_cache` is `True` (the default); otherwise the cached value survives
close, ready to be returned again without re-running the creator.

### Reopen (context-manager protocol)

`Container` implements both sync (`__enter__` / `__exit__`) and async (`__aenter__` / `__aexit__`)
context managers; `open()` (documented on the method itself) is the reopen primitive they call.

Concretely: using the same container object as a context manager a second time reopens it (clears
`closed`), resolves providers fresh if `clear_cache=True` was set on their `CacheSettings` (since
close removed those cached values), and then closes it again on exit. Providers whose
`CacheSettings.clear_cache` is `False` retain their cached instances across reopen cycles.

Prefer the `with` form. `open()` is exposed as a public method for callback-style lifecycles that
cannot wrap the container in a `with` block — for example a framework startup hook that must reopen
the long-lived root container before serving the next request. The FastStream integration uses
exactly this: `app.on_startup(container.open)` paired with `app.after_shutdown(container.close_async)`.

## `validate()`

See [validation.md](validation.md) for what `container.validate()` checks, how it reports
aggregated errors, and the pending 3.0 default flip.

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
