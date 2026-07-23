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
| `validate` | `True` | Enable the provider-graph check, run once at `open()`. `False` disables it. See below. |

A root container (no `parent_container`) creates fresh `ProvidersRegistry` and `OverridesRegistry`
instances. It also auto-registers `container_provider` (see [below](#container_provider)) under the
`Container` type.

A freshly-constructed container starts **unopened** (`closed = True`) and must be entered before use —
see [Mandatory-open lifecycle](#mandatory-open-lifecycle).

### `validate` (a plain bool)

See [validation.md](validation.md) for what the check does and why. `validate` is a plain
`bool = True`: the default and `True` enable the provider-graph check, which runs **once at `open()`**
(never in `__init__`, never on resolve); `validate=False` disables it. `__init__` records this once as
`self._validate_enabled = validate and parent_container is None`. The `parent_container is None`
conjunct is the container-specific wrinkle: only a **root** validates. A child built via
`build_child_container` never passes `validate`, and even if it did the `parent_container is None` guard
is false for every child, so `_validate_enabled` is always `False` on a child — children never validate,
regardless of `validate`'s value. That is safe because the providers registry is shared tree-wide, so
the root's single validation walk covers every child (see [Integration seam](#integration-seam)).

## Mandatory-open lifecycle

A container must be **opened** before it can resolve or build children. Construction leaves it
unopened (`closed = True`); calling `resolve` / `resolve_provider` / `resolve_dependency` /
`build_child_container` on an unopened (or closed) container raises `ContainerClosedError`. Enter it
via `with` / `async with`, or call `open()` directly:

```python
with Container(scope=Scope.APP, groups=[MyGroup]) as container:
    container.resolve(...)  # opened -> usable; validated once on entry (root only)
# exit closes it; re-entering reopens

# callback-style lifecycle (no with-block available):
container = Container(scope=Scope.APP, groups=[MyGroup])
container.open()  # opens + validates (root, once)
```

The full lifecycle is: **construct → (unopened: use raises) → `open()`/`with` (root validates once) →
use → close → reopen**. `open()` is the single validation trigger — resolution never validates. Only a
root validates; a child from `build_child_container` also starts unopened and must be entered, but its
`open()` merely clears `closed` (children never validate). See
[Lifecycle: close and reopen](#lifecycle-close-and-reopen) for close/reopen mechanics.

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
- Building a child requires the parent be **open**: `build_child_container` on an unopened or closed
  parent raises `ContainerClosedError` (see [Lifecycle: close and reopen](#lifecycle-close-and-reopen)
  below). The returned child itself starts unopened and must be entered before use.

  This guard is **not** redundant with the resolve-time closed-check, and that is why it is kept.
  A compiled resolver navigates to the scope-owning container and checks *its* `closed` flag
  ([resolution.md](resolution.md) / `resolver_compiler.py`), so a resolve that reaches an unopened
  ancestor does raise on its own. But a provider resolvable **at the open child's own scope**
  (`target == container`) skips every ancestor closed-check, and children never validate
  ([validate](#validate-a-plain-bool) — validation runs only at *root* `open()`). Without this
  guard you could build a child off a never-opened root, open the child, and resolve child-scoped
  providers against a graph whose cycles/scope errors were **never checked**. The build guard is
  the single enforcement point that forces `root.open()` (hence validation) to happen before any
  child can exist and resolve.

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

2. **`closed = True`** — always set in a `finally` block, even if finalizers raised. A subsequent
   `resolve_provider` / `build_child_container` (or a nested provider resolving at a closed ancestor
   scope) raises `ContainerClosedError` — there is no self-heal. Re-enter the container via
   `with`/`async with`, or call `container.open()`, before reusing it.

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

`Container` implements both sync (`__enter__` / `__exit__`) and async (`__aenter__` / `__aexit__`)
context managers; `open()` (documented on the method itself) is the primitive they call — both to open
a freshly-constructed container the first time and to reopen it on re-entry.

Concretely: using the same container object as a context manager a second time reopens it (clears
`closed`), resolves providers fresh if `clear_cache=True` was set on their `CacheSettings` (since
close removed those cached values), and then closes it again on exit. Providers whose
`CacheSettings.clear_cache` is `False` retain their cached instances across reopen cycles.

`open()` also runs validation, but **only once**: it calls `self.validate()` when
`_validate_enabled and not self._validated` (root only). `close()` leaves `_validated` untouched (it
only sets `closed = True`), so the flag survives a close, and a plain close→reopen does **not** re-walk
the graph. See [validation.md](validation.md#enabling-validation--deferred-by-default).

Prefer the `with` form. `open()` is exposed as a public method for callback-style lifecycles that
cannot wrap the container in a `with` block — for example a framework startup hook that must open the
long-lived root container before serving the first request (and reopen it after a shutdown). The
FastStream integration uses exactly this: `app.on_startup(container.open)` paired with
`app.after_shutdown(container.close_async)`.

## `validate()`

See [validation.md](validation.md) for what `container.validate()` checks, how it reports
aggregated errors, and how validation runs once at `open()` by default.

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
