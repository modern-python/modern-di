# Container Validation

`Container.validate()` audits the static provider graph for wiring errors before any dependency is resolved. It
is the authoritative catch-all for three classes of bug: **circular dependencies**, **inverted scope
dependencies**, and **missing required dependencies**.

## Enabling validation

Pass `validate=True` when constructing a container to run validation immediately after all groups are registered:

```python
container = Container(scope=Scope.APP, groups=[MyGroup], validate=True)
```

Or call `container.validate()` explicitly at any point after construction:

```python
container = Container(scope=Scope.APP, groups=[MyGroup])
container.validate()  # raises ValidationFailedError if any issue found
```

`validate` is tri-state (`bool | None`, default `None`) — see the [constructor table](containers.md#creating-a-root-container)
for the full parameter reference. `validate=True` runs validation inside `__init__` (equivalent to
`Container(...); container.validate()`); `validate=False` skips it silently with zero runtime cost;
leaving it unset (`None`) also skips it but emits `UnvalidatedContainerWarning` on a **root**
container, because **modern-di 3.0 runs `validate()` at root construction by default** — the
current opt-in becomes opt-out. Pass `validate=True` now to adopt the 3.0 behavior early, or
`validate=False` to keep it off permanently (that stays a supported no-warning choice after 3.0).
See the [migration guide](../docs/migration/to-3.x.md) for the full readiness recipe. (Child
containers never emit this warning regardless of `validate` — see
[containers.md](containers.md#validates-three-states).)

## What validate() checks

`validate()` is a **fold** over one depth-first walk of the provider graph:
`DependencyGraph().walk(providers_registry, self)` (in `modern_di/dependency_graph.py`) runs a single
iterative, explicit-stack traversal and yields an event stream — `NodeEntered`, `Edge`, `Cycle`,
`DependenciesError` — while `validate()` applies one policy per event kind (`NodeEntered` →
`iter_validation_issues`; `Edge` → the scope-ordering check; `Cycle` → `CircularDependencyError`;
`DependenciesError` → collect the raised exception). The walk emits *structure*; `validate()` supplies
*policy*. That same walker also backs the runtime cycle guard (see the blockquote below), so the two
share one traversal — a stance reversed, on the extraction axis only, from the "deliberate duplication"
defense this file once carried; the reasoning is recorded in
[decisions/2026-07-12-unify-graph-traversal.md](../planning/decisions/2026-07-12-unify-graph-traversal.md).

It collects **all errors** across the entire walk before raising, so a single call surfaces all wiring
bugs at once rather than stopping at the first one. `validate()` raises `exceptions.ValidationFailedError`
if any are found; its `.errors` attribute lists every collected exception, and its `__str__` groups them
by class name so a report mixing several error kinds reads as one section per kind — see
`ValidationFailedError.__str__` in `modern_di/exceptions.py`. Validation runs entirely against
`providers_registry`, so a root APP-scope container validates deeper-scoped providers without building
child containers.

**The graph it walks is the graph that resolves.** Edges come from `WiringPlan.edges`, a view *derived*
from the same buckets `resolve()` reads (`provider_kwargs` + `context_kwargs`) rather than assembled
separately — so the validated graph cannot drift from the resolved one. In particular a provider supplied
via a declaration-time `kwargs={...}` is an edge like any type-matched one, and a cycle or scope inversion
routed through it is caught here rather than surfacing at resolve time as a bare `RecursionError` or a
`ScopeNotInitializedError`. See [resolution.md](resolution.md) for how the buckets are filled.

**Validated-version short-circuit.** `ProvidersRegistry` carries a `validated_version: int | None`. On a
successful walk `validate()` stamps `validated_version = version`; a later `validate()` whose
`validated_version == version` returns immediately without re-walking, so a repeat `validate()` is free.
Every registry mutation (`register` / `add_providers` / `_remove_providers`) bumps `version` and resets
`validated_version = None`, so any change to the graph re-arms both `validate()` and the runtime guard.
The stamp lives on the registry, which is shared tree-wide, so validating any one container marks the
graph clean for every container in the tree.

### Circular dependencies

When the walk follows an edge to a provider still on the active path (tracked in the walk's internal
`visiting` set), it emits a `Cycle` event whose `providers` list closes the loop by repeating the first
node last (e.g., `[A, B, A]`). `validate()` maps that event to a `CircularDependencyError` (built via
`dependency_graph.build_cycle_error`), which carries the loop as `.steps` — one `ResolutionStep`
(scope, name, optional definition site) per node. Before rendering, `build_cycle_error` rotates the loop
to start at its minimum-`provider_id` node, so the same cycle renders identically no matter which
provider the walk happened to seed from. The walk does **not** descend into the cycle, but the
rest of the graph continues to be checked. `CircularDependencyError.__str__` renders those steps as a
multi-line arrow chain, not an inline `A -> B -> A` string.

`.cycle_path` (the bare list of type names, e.g. `["A", "B", "A"]`) and `.cycle_locations` (the parallel
`module:line` anchors) are **views derived from `.steps`**, so they cannot fall out of step with each
other or with what is rendered — the equal-length invariant is structural rather than enforced at render
time. Definition sites use the same lazy, memoized, best-effort capture described for breadcrumb steps in
[resolution.md](resolution.md#breadcrumb-definition-sites).

Because a `ResolutionStep` carries its provider's scope, the cycle renders through the *same* chain drawer
as a resolution breadcrumb — including the aligned scope column — so a cycle and a failed resolution path
read identically. See [resolution.md](resolution.md#one-renderer) for that drawer.

> **Runtime resolution has a cycle guard too — but `validate()` remains the way to see all errors up front.**
> `Container.resolve_provider` wraps the final `provider.resolve(self)` in `try/except RecursionError`. The
> handler first short-circuits: if the registry is already validated (`validated_version == version`), the static
> graph is known acyclic, so the overflow is genuine self-recursion and the `RecursionError` re-raises untouched
> without any walk. Otherwise, when an unvalidated circular graph's first resolve overflows the stack, the handler
> re-walks the static graph from the failing provider via `DependencyGraph().find_cycle_from` — the same
> iterative, explicit-stack `walk` that `validate()` uses (it must stay flat, since it runs close to the recursion
> limit) — and, if a static cycle is reachable, raises `CircularDependencyError` (built by
> `dependency_graph.build_cycle_error`) with the cycle path, `from` the original `RecursionError`.
> `resolve_provider` is re-entrant (`Factory`/`Alias` call it per dependency edge), so it is the innermost frame
> that converts. `CircularDependencyError.prepend_step` overrides the breadcrumb machinery every other
> `ResolutionError` uses (see [resolution.md](resolution.md)) as a no-op, so an outer frame unwinding past the
> conversion adds nothing to it: the error is already self-contained the moment `build_cycle_error` constructs it,
> naming every provider in the loop canonically rooted at its minimum-`provider_id` node — not a partial breadcrumb
> an outer frame still needs to complete. A `RecursionError` from a creator that recurses on its own (no static
> cycle in the graph) is re-raised untouched, not misreported as a circular dependency. Both the guard and
> `validate()` consume
> the one `DependencyGraph` walker: `validate()` collects *all* errors of *all* kinds up front, while the guard
> only answers "is a cycle reachable from here" on an already-exhausted stack. Run with `validate=True` (or call
> `container.validate()`) in development to surface *every* cycle (and other wiring bugs) before the first resolve,
> rather than only the one a particular resolve happens to hit.

### Inverted scope dependencies

For every dependency edge `provider → dep` (the walk's `Edge` event), `validate()` compares their
**terminal scopes** (see below). If `dep`'s terminal scope is strictly deeper than `provider`'s terminal
scope, the dependency is inverted: a shallower-lived provider cannot hold a reference to a deeper-lived
one. The error is recorded as `InvalidScopeDependencyError` (see `exceptions.py` for the exact message),
which names the provider, the parameter, the dependent provider, and the offending scopes. The walk
continues into the dependency so further issues in that subtree are also surfaced.

### Missing required dependencies

When the walk enters a provider (the `NodeEntered` event, emitted before that provider's dependencies are
read), `validate()` calls `provider.iter_validation_issues(container)` and appends any returned exceptions
to the error list. `Factory` implements this hook to yield `ArgumentResolutionError` for each constructor
parameter that has no matching provider in `providers_registry`, no default value, and no static `kwargs`
entry.

## Terminal scope and alias transparency

`validate()`'s scope-ordering check uses `DependencyGraph.terminal_scope(provider, container)` on both
sides of every dependency edge — not `provider.scope` directly.

`terminal_scope` follows the `AbstractProvider.redirect_target(container)` node hook from provider to
provider until it reaches one whose resolution terminates there (`redirect_target` returns `None`), then
returns that terminal provider's `.scope`. The hook defaults to `None` on `AbstractProvider`, so for most
providers `terminal_scope` returns `self.scope` in a single step. `Alias` overrides `redirect_target` to
return its source provider (and `None` when the source type is unregistered), so `terminal_scope` follows
an alias chain to its terminal non-alias target and reports **that provider's scope**. This makes
validation transitive through aliases. Consider:

```
Factory(scope=APP, creator=Caller)   # depends on IFace
Alias(source_type=Impl, bound_type=IFace)  # no scope parameter
Factory(scope=REQUEST, creator=Impl)
```

The alias's terminal scope is `REQUEST` (the scope of `Impl`). When `validate()` checks the `Caller → IFace`
edge, it compares `APP` against `REQUEST` and raises `InvalidScopeDependencyError`. Without `terminal_scope`,
the alias's own `scope` attribute (defaulting to `APP`) would mask the true depth of the dependency.

Two edge cases in `terminal_scope` are handled safely:

- **Redirect cycle**: if the chain revisits a provider (tracked in `terminal_scope`'s `seen` set), it
  breaks out and falls back to the starting provider's own `.scope` instead of looping forever. The cycle
  itself is separately detected and reported as a `Cycle` event by the walk, which traverses the same
  `source` edge.
- **Dangling source**: if an alias's source type is not registered, `redirect_target` returns `None`, so
  `terminal_scope` stops at the alias and falls back to its `.scope`. The dangling source is separately
  reported by the alias's dependency lookup raising `AliasSourceNotRegisteredError` during the walk
  (a `ResolutionError`, surfaced as a `DependenciesError` event).

## Exception types

| Exception | Base | Raised by |
|---|---|---|
| `ValidationFailedError` | `ContainerError` | `Container.validate()` — aggregate wrapper |
| `CircularDependencyError` | `ResolutionError` | recorded inside `validate()` on cycle detection |
| `InvalidScopeDependencyError` | `RegistrationError` | recorded inside `validate()` on inverted scope edge |
| `ArgumentResolutionError` | `ResolutionError` | yielded by `Factory.iter_validation_issues()` |

Every concrete `ModernDIError` subclass — these three included — carries a class-level `docs_slug`
naming its page under `docs/troubleshooting/`; the census test (`tests/test_docs_slug_census.py`)
pins both that every slug is set and unique and that its page actually exists, so a new exception
cannot ship without a matching troubleshooting page.
