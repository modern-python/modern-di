# Scopes

`Scope` is an `IntEnum` defined in `modern_di/scope.py`. It has five named levels:

```
APP = 1  →  SESSION = 2  →  REQUEST = 3  →  ACTION = 4  →  STEP = 5
```

Higher integer values represent deeper (more short-lived) scopes. The ordering is significant: the integer value
determines both the scope hierarchy and the validity rules for provider resolution.

## Resolution rule

Every provider is bound to a scope at declaration time. The rule is:

> A provider bound to scope **S** may only be resolved from a container whose scope is **S or deeper**
> (i.e., `container.scope >= provider.scope`).

Attempting to resolve a provider from a container whose scope is shallower than the provider's scope raises one of
two exceptions, depending on what went wrong (see `exceptions.py` for the exact messages):

- **`ScopeNotInitializedError`** — raised when the required scope is deeper than the resolving container's scope
  (the child container for that scope has not been built yet).
- **`ScopeSkippedError`** — raised when the required scope is shallower than the resolving container's scope but
  is not present anywhere in the ancestor chain (i.e., the chain was started at a scope that skipped it).

Both exceptions inherit from `ContainerError → ModernDIError → RuntimeError`.

Both also carry a breadcrumb `dependency_path` (via the shared `DependencyPathMixin` — see the scope
walk in [resolution.md](resolution.md)), so a **captive dependency** (a shallower-scoped provider that,
directly or transitively, depends on a deeper-scoped one) reports both the capturing provider's name
and the one that actually failed to resolve, in addition to the two scope names. Raised with an empty
path (e.g. a bare `find_container` call with no provider frame involved), the message falls back to
the base one-liner with no breadcrumb prepended.

## How the container locates the right-scope container

Each `Container` maintains a `scope_map: dict[IntEnum, Container]`. When a root container is created, the map is
`{scope: self}`. Each child container extends the map: `{**parent.scope_map, child_scope: child}`.

`Container.find_container(scope)` performs the lookup:

1. If `scope` is in `scope_map`, return the corresponding container immediately — no tree walk needed.
2. If `scope` is not in `scope_map` and `scope > self.scope`, raise `ScopeNotInitializedError` (the required
   child container has not been built yet).
3. If `scope` is not in `scope_map` and `scope <= self.scope`, raise `ScopeSkippedError` (the scope was
   never present in this chain).

The `scope_map` is built incrementally at construction time, so lookups are O(1). There is no runtime
parent-chain traversal during resolution.

## Custom scopes

`Scope` is a convenience enum, but `Container` accepts any `enum.IntEnum` member as its scope. Teams that need
more levels (or different names) can define their own `IntEnum` and use it throughout. The same integer-ordering
rules apply. Passing a non-`IntEnum` value raises `InvalidScopeTypeError`.

A custom scope is a **standalone** `IntEnum`, never a subclass of `Scope` — Python forbids extending an enum
that has members (`class MyScope(Scope)` raises `TypeError: cannot extend enumeration 'Scope'`).

## The scope algebra

The one rule that is not just an integer comparison — *"which members of my enum are deeper than me"* — lives in
`scope.py`, next to the concept it belongs to:

- `_deeper_members(scope)` — the members of `scope`'s own enum deeper than it, shallowest first.
- `_next_deeper(scope)` — the shallowest of those, or `None` at the deepest member.

Both take **any** `IntEnum`, which the custom-scope contract forces: since a custom scope cannot subclass
`Scope`, an algebra expressed as methods on `Scope` would silently apply to the five built-in members and to
nothing else. Free functions apply uniformly, so custom scopes get the rule for free.

`scope.py` imports only `enum` and stays that way by necessity: `exceptions.py` imports `_deeper_members` (to
derive `InvalidChildScopeError.allowed_scopes`), so `_next_deeper` returns `None` at the deepest member rather
than raising `MaxScopeReachedError` itself — raising it here would make `scope` import `exceptions` and the two
would cycle. `Container.build_child_container` owns that raise.

Both consumers read the rule from this one home: `build_child_container` derives an omitted child scope with
`_next_deeper`, and `InvalidChildScopeError` reports the valid choices with `_deeper_members`. The plain
ordering checks (`scope <= parent.scope`, `scope > self.scope`) stay as they are — `IntEnum` already gives
comparison for free, and wrapping it would add an interface without adding a rule.

## See also

- [docs/providers/scopes.md](../docs/providers/scopes.md) for a worked, user-facing walk-through of
  resolving across scopes and building child containers.
- [containers.md](containers.md#child-containers) for `build_child_container`'s scope rules
  (auto-increment, `MaxScopeReachedError`).
