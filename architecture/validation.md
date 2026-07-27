# Container Validation

`Container.validate()` audits the static provider graph for wiring errors before any dependency is resolved. It
is the authoritative catch-all for three classes of bug: **circular dependencies**, **inverted scope
dependencies**, and **missing required dependencies**.

## Enabling validation: monotone at construction, complete at first use

Validation is enabled by default and splits into two halves that run at different times, because the
two halves behave differently against a graph that is not yet complete:

- **Monotone half (cycles, inverted scopes) — `__init__`.** Registering more providers can only ever
  *add* a cycle or an inverted-scope edge, never remove one that was already there: a missing
  dependency contributes no edge at all — there is nothing yet to walk into. So an incomplete graph
  can only ever *under*-report these two checks, with one carve-out below. That makes them safe to
  run the moment a root container is constructed, before any integration has had a chance to register
  its own providers.

  **The dangling-redirect carve-out.** A dangling `Alias` — one whose source type is not registered —
  has no terminal provider to read a scope from, so `terminal_scope` falls back to the alias's own
  hardcoded `Scope.APP` (see
  [Terminal scope and alias transparency](#terminal-scope-and-alias-transparency)). That value is a
  *placeholder*, not a measurement: `Scope.APP` is the minimum only over the built-in `Scope`, and
  [scopes.md](scopes.md) accepts any standalone `IntEnum`, whose members may sit below it. An edge
  whose dependency side terminates on a dangling redirect could therefore be reported as inverted
  against a scope the real source never had. So that one case is classified **non-monotone** and
  deferred to the completeness half instead of raised from `__init__`. Nothing is lost: the dangling
  alias is already reported as a completeness error in its own right
  (`AliasSourceNotRegisteredError`), and once the source is registered the re-walk reads the true
  terminal scope and reports any genuine inversion then. Only the *dependency* side needs this
  treatment — a dangling alias raises from `get_dependencies`, so it never emits an edge as a
  *parent*, and a redirecting parent always shares its dependency's terminal provider, making the
  two scopes equal and the edge un-inverted by construction.
- **Completeness half (missing dependencies, dangling aliases) — first use.** Both depend on the graph
  actually being complete: a provider missing at construction time may still be registered a moment
  later via [`add_providers`](containers.md#integration-seam). Raising eagerly would fail on a graph a
  framework integration has not finished assembling yet, so this half is held and checked once the
  graph is actually used.

```python
container = Container(scope=Scope.APP, groups=[MyGroup])  # __init__ raises a cycle or inverted scope now
container.resolve(...)  # first use raises any held completeness errors, then resolves
```

`validate` is a plain `bool` (default `True`) — see the [constructor table](containers.md#creating-a-root-container)
for the full parameter reference. `True` (the default) enables both halves; `validate=False` disables
both entirely, with zero runtime cost — no walk ever runs, at construction or otherwise. For an
immediate, full check of both halves, call `container.validate()` explicitly:

```python
container = Container(scope=Scope.APP, groups=[MyGroup])
container.validate()  # runs now, both halves; raises ValidationFailedError if any issue found
```

Only a **root** container's `__init__` walks the graph; children (built via `build_child_container`)
never do. That is safe because all three pieces of validation state live on the shared
`ProvidersRegistry` — not on any individual `Container` (`Container` has no per-container validated
flag):

- **the enabled bit** — `ProvidersRegistry.is_validation_enabled()`, written once by the root that owns
  the registry, from its `validate` argument;
- **the pending completeness errors** — `ProvidersRegistry.has_pending_errors()` /
  `take_pending_errors()`, set by whichever walk found them and consumed by whichever container is
  prepared first;
- **the `_validated` flag** — see *Once only*, below.

Because the registry is shared tree-wide, whichever container in the tree is used first — root or
child, via the private `_prepare()` the resolve path calls on a closed container (see
[Optional-open lifecycle](containers.md#optional-open-lifecycle)) — completes the deferred half for the
whole tree. The gate is `not reg.is_validated() and (reg.is_validation_enabled() or
reg.has_pending_errors())`. The `has_pending_errors()` disjunct matters for a `validate=False` root that
still called `container.validate()` manually: `is_validation_enabled()` is `False` forever on that
registry, so without also checking for pending errors, completeness errors a later `add_providers` call
deferred would be dead state nothing could ever surface.

**Once only.** `ProvidersRegistry` carries a `_validated: bool`, set once a walk finds no errors of
either kind. A root's `__init__` walk that finds a clean graph marks it validated immediately, so the
runtime `RecursionError`-to-`CircularDependencyError` guard (see the blockquote below) short-circuits
from construction onward, not just from first use. Every registry mutation (`register` /
`add_providers` / `_remove_providers`) clears `_validated` back to `False`, so any change to the graph
re-arms both the deferred completeness check and the runtime guard. A plain `close()` / reopen never
touches the registry, so it never re-arms validation on its own — validation is paid exactly once per
registry state, however many containers in the tree end up preparing.

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

**Validated-flag short-circuit.** `ProvidersRegistry` carries a `_validated: bool`, set by `mark_validated()`
on a successful walk; a later `validate()` while `_validated` is still `True` returns immediately without
re-walking, so a repeat `validate()` is free. Every registry mutation (`register` / `add_providers` /
`_remove_providers`) clears `_validated` back to `False`, so any change to the graph re-arms both
`validate()` and the runtime guard. The flag lives on the registry, which is shared tree-wide, so validating
any one container marks the graph clean for every container in the tree.

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
> `Container.resolve_provider` wraps the compiled-resolver dispatch (`resolver_for(provider)(self)`) in
> `try/except RecursionError`. The
> handler first short-circuits: if the registry is already validated (`_validated` is `True`), the static
> graph is known acyclic, so the overflow is genuine self-recursion and the `RecursionError` re-raises untouched
> without any walk. Otherwise, when an unvalidated circular graph's first resolve overflows the stack, the handler
> re-walks the static graph from the failing provider via `DependencyGraph().find_cycle_from` — the same
> iterative, explicit-stack `walk` that `validate()` uses (it must stay flat, since it runs close to the recursion
> limit) — and, if a static cycle is reachable, raises `CircularDependencyError` (built by
> `dependency_graph.build_cycle_error`) with the cycle path, `from` the original `RecursionError`.
> `resolve_provider` is re-entrant: a cycle's back-edge is compiled as a thunk that routes back through it (a
> provider whose resolver was still under construction — see [resolution.md](resolution.md#cycle-safe-compilation)),
> so a loop stacks one `resolve_provider` frame per back-edge and the innermost one converts.
> `CircularDependencyError.prepend_step` overrides the breadcrumb machinery every other
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

`validate()`'s scope-ordering check uses `DependencyGraph.terminal_provider(provider, container)` on both
sides of every dependency edge — not `provider.scope` directly. `terminal_scope(provider, container)` is
the thin `.scope` accessor over it, for callers that need only the verdict.

`terminal_provider` follows the `AbstractProvider.redirect_target(container)` node hook from provider to
provider until it reaches one whose resolution terminates there (`redirect_target` returns `None`), then
returns that terminal provider, whose `.scope` is the answer. The hook defaults to `None` on
`AbstractProvider`, so for most providers the terminal is the provider itself, in a single step. `Alias` overrides `redirect_target` to
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

Two edge cases in the walk are handled safely:

- **Redirect cycle**: if the chain revisits a provider (tracked in `terminal_provider`'s `seen` set), it
  breaks out and returns the last provider on the chain instead of looping forever. The cycle
  itself is separately detected and reported as a `Cycle` event by the walk, which traverses the same
  `source` edge.
- **Dangling source**: if an alias's source type is not registered, `redirect_target` returns `None`, so
  the chain stops at the alias and its own `.scope` (`Scope.APP`) stands in. The dangling source is
  separately reported by the alias's dependency lookup raising `AliasSourceNotRegisteredError` during
  the walk (a `ResolutionError`, surfaced as a `DependenciesError` event). Because that scope is a
  placeholder, `AbstractProvider.has_dangling_redirect(container)` — `False` by default, overridden by
  `Alias` to test its source's registration — tells the two apart, and an inversion measured against a
  dangling terminal is classified non-monotone (see
  [the carve-out](#enabling-validation-monotone-at-construction-complete-at-first-use)).

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
