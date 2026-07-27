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
| `validate` | `True` | Enable the provider-graph check: the monotone half (cycles, inverted scopes) runs in `__init__`; the completeness half (missing dependencies, dangling aliases) is deferred to first use. `False` disables both. See below. |

A root container (no `parent_container`) creates fresh `ProvidersRegistry` and `OverridesRegistry`
instances. It also auto-registers `container_provider` (see [below](#container_provider)) under the
`Container` type.

A freshly-constructed container starts **closed** (`closed = True`) but is usable immediately — see
[Optional-open lifecycle](#optional-open-lifecycle).

### `validate` (a plain bool)

See [validation.md](validation.md) for what the check does, why it splits by monotonicity, and where
each half runs. `validate` is a plain `bool = True`: the default and `True` enable the provider-graph
check; `validate=False` disables it entirely, with zero runtime cost, and no construction-time or
first-use walk ever happens. `__init__` records the per-container gate once as
`self._validate_enabled = validate and parent_container is None`. The `parent_container is None`
conjunct is the container-specific wrinkle: only a **root**'s constructor walks the graph. A child
built via `build_child_container` never passes `validate`, and even if it did the
`parent_container is None` guard is false for every child, so `_validate_enabled` is always `False`
there — a child's `__init__` never walks. That is safe because the providers registry is shared
tree-wide: when `_validate_enabled` is true, the root's `__init__` walk raises monotone errors (cycles,
inverted scopes) immediately and holds any completeness errors on that shared registry for whichever
container in the tree is prepared first — root or child (see [Integration seam](#integration-seam)).

## Optional-open lifecycle

A constructed container is usable immediately — there is no required `open()` step. The first
`resolve` / `resolve_provider` / `resolve_dependency` that reaches a closed container (directly, or by
building a child and resolving through it) calls the private `_prepare()`, which finishes any deferred
validation (see [validation.md](validation.md#enabling-validation)) and then clears `closed`. `open()`
and `with` / `async with` stay available — call them to fail fast at startup, before the first unit of
work, and to get finalizers on the way out:

```python
container = Container(scope=Scope.APP, groups=[MyGroup])
container.resolve(...)  # closed=True -> _prepare() runs silently -> resolves

# fail-fast + finalizers:
with Container(scope=Scope.APP, groups=[MyGroup]) as container:
    container.resolve(...)
# exit closes it; re-entering (or an implicit resolve) reopens it
```

Three states, tracked by the public `closed: bool` plus a private `_ever_closed: bool` (set `True` in
the `finally` block of both `close_sync()` and `close_async()`, never reset):

| State | `closed` | `_ever_closed` | Implicit use | `open()` / `with` |
|---|---|---|---|---|
| New | `True` | `False` | prepares silently | prepares, silent |
| Open | `False` | either | proceeds | no-op |
| Closed | `True` | `True` | prepares, warns | prepares, silent |

The discriminator is *has this container been closed*, not *has it been opened*: a container
constructed, closed, and then used lands in the Closed row — because the user called `close_sync()` /
`close_async()` on it, not because it was never opened. Reusing a closed container **implicitly** (a
resolve that reaches it without going through `open()` / `with` first) reopens it and emits
`ContainerClosedWarning` (a `RuntimeWarning`, so it is visible outside `__main__`, unlike
`DeprecationWarning`); calling `open()` explicitly reopens silently, since a deliberate reopen is not a
diagnostic-worthy event. See [Lifecycle: close and reopen](#lifecycle-close-and-reopen) for what close
and reopen do to the cache, and [Open and reopen](#open-and-reopen-context-manager-protocol) for
`_prepare()` / `open()` mechanics.

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
  nothing and touches no cache, so a closed (or never-prepared) parent is irrelevant to it — there is no
  closed-check on the parent. The returned child itself starts closed, same as any freshly-constructed
  container; see [Optional-open lifecycle](#optional-open-lifecycle).

  This is safe because validation state lives on the shared `ProvidersRegistry`, not on any one
  container ([validate](#validate-a-plain-bool); [validation.md](validation.md)). When validation is
  enabled, the root's `__init__` walk raises monotone errors (cycles, inverted scopes) immediately and
  holds any completeness errors on that registry. Because the registry is shared tree-wide, **any**
  container's first touch — root or child — completes the deferred half via `_prepare()`, so a graph
  can never be resolved against without the completeness check having run somewhere in the tree first.
  Building a child off a closed or never-prepared parent therefore skips nothing: the graph is checked
  either at root construction (monotone half) or at whichever container in the tree is used first
  (completeness half).

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
registry it mutates is shared tree-wide. All validation state lives on the
shared `ProvidersRegistry`, not on `Container` — there is no per-container
validated flag (see [validation.md](validation.md#what-validate-checks)).
Before mutating, `add_providers` reads `recheck = reg.is_validation_enabled() or
reg.is_validated()` — read **before** the mutation, because mutating the
registry immediately clears `is_validated()`. It then registers the new
providers and, if `recheck` was true, re-runs the monotone half of the walk
against the whole (now-larger) graph: a cycle or inverted scope introduced by
the new batch raises, and the *entire* batch is rolled back — the registry
ends up either fully registered and valid-so-far, or unchanged. Completeness
errors found by that same walk are not raised; they are re-deferred to first
use, exactly like the construction-time walk, since a later `add_providers`
call may still complete the graph. Because the registry is shared tree-wide, a
batch registered through the root is immediately visible — and, once
validated, immediately clean — to every container in the tree, so a child's
`resolve` benefits from a root's `add_providers` call without the child ever
calling `validate()` itself. `resolve_dependency` carries no such restriction;
it is a resolve verb, callable on any container regardless of validation
state.

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

2. **`closed = True`** and **`_ever_closed = True`** — both always set in a `finally` block, even if
   finalizers raised. A subsequent `resolve_provider` (or a nested provider resolving at a closed
   ancestor scope) self-heals: it reopens the container via `_prepare()` and emits
   `ContainerClosedWarning`, rather than raising. Re-enter the container via `with`/`async with`, or
   call `container.open()`, for a silent reopen instead — see
   [Optional-open lifecycle](#optional-open-lifecycle).

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
compiled-resolver dispatch it wraps) calls it on a closed container before doing anything else, and it
is a no-op once `closed` is `False`. `open()` is a separate, public entry point with the same effect
minus the closed-check and the reuse warning: it always finishes any deferred validation and clears
`closed`, whether the container was closed or already open. `Container` implements both sync
(`__enter__` / `__exit__`) and async (`__aenter__` / `__aexit__`) context managers; both call `open()`
on entry and `close_sync()` / `close_async()` on exit.

Concretely: using the same container object as a context manager a second time reopens it (clears
`closed`), resolves providers fresh if `clear_cache=True` was set on their `CacheSettings` (since
close removed those cached values), and then closes it again on exit. Providers whose
`CacheSettings.clear_cache` is `False` retain their cached instances across reopen cycles.

`open()` runs `_ensure_ready()` **unconditionally**, with no `if self.closed:` guard — deliberately,
since `open()` is the fail-fast verb: calling it on an already-open container must still surface
validation the registry is holding, such as completeness errors a later
[`add_providers`](#integration-seam) call left pending. In practice this costs nothing once the graph
is clean, since `ProvidersRegistry.is_validated()` short-circuits the walk (see
[validation.md](validation.md#enabling-validation)); `_prepare()`, by contrast, does have a (lock-held,
re-checked) `if self.closed:` guard, since its job is only to catch a container's first use, not to
re-verify an already-open one on every call.

`open()` is optional — see [Optional-open lifecycle](#optional-open-lifecycle) — but prefer the `with`
form, or an explicit `open()` call, over relying on implicit first-use preparation: both fail fast, at
startup rather than on the first unit of work, and run finalizers on the way out. `open()` is exposed
as a public method for callback-style lifecycles that cannot wrap the container in a `with` block — for
example a framework startup hook that opens the long-lived root container before serving the first
request (and reopens it after a shutdown). The FastStream integration uses exactly this:
`app.on_startup(container.open)` paired with `app.after_shutdown(container.close_async)`. With `open()`
optional, that pairing is no longer needed to avoid a hard failure on the first request — the root
would prepare itself either way — it remains valuable for fail-fast startup and for placing finalizers
at a well-defined shutdown hook.

## `validate()`

See [validation.md](validation.md) for what `container.validate()` checks, how it reports
aggregated errors, and how the check splits by monotonicity between `__init__` and first use
by default.

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
