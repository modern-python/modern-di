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

`validate()` performs a depth-first search (DFS) over every provider in `providers_registry` (the walk itself is
`Container.validate()` in `modern_di/container.py`). It collects **all errors** across the entire walk before
raising, so a single call surfaces all wiring bugs at once rather than stopping at the first one. `validate()`
raises `exceptions.ValidationFailedError` if any are found; its `.errors` attribute lists every collected
exception, and its `__str__` groups them by class name so a report mixing several error kinds reads as one
section per kind — see `ValidationFailedError.__str__` in `modern_di/exceptions.py`. Validation runs entirely
against `providers_registry`, so a root APP-scope container validates deeper-scoped providers without building
child containers.

### Circular dependencies

During the DFS, a provider encountered a second time while it is still on the active path (i.e., it appears in
`visiting`) means a cycle exists. `validate()` records a `CircularDependencyError` with a `.cycle_path` list of
type names showing the loop (e.g., `["A", "B", "A"]`). The recursive walk does **not** continue into the cycle,
but the rest of the graph continues to be checked. `CircularDependencyError.__str__` renders `.cycle_path` as a
multi-line arrow chain, not an inline `A -> B -> A` string — see `CircularDependencyError` in `exceptions.py`.

Each node in that chain may also carry an optional definition site — the creator's declaration
point — rendered as a trailing `module:line` anchor alongside the provider name, using the same
lazy, memoized, best-effort capture described for breadcrumb steps in
[resolution.md](resolution.md#breadcrumb-definition-sites). The public `.cycle_path` stays the bare
list of type names; the parallel locations live on a separate `.cycle_locations` attribute. Both
`validate()` and the runtime guard build the error through the one `dependency_graph.build_cycle_error`
helper, so the two attributes stay in sync by construction rather than by parallel edit.

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
> that converts; outer frames see a `ResolutionError` and the existing breadcrumb machinery (see
> [resolution.md](resolution.md)) prepends steps as it propagates back up, so the converted error arrives with the
> dependency chain attached. A `RecursionError` from a creator that recurses on its own (no static cycle in the
> graph) is re-raised untouched, not misreported as a circular dependency. Both the guard and `validate()` consume
> the one `DependencyGraph` walker: `validate()` collects *all* errors of *all* kinds up front, while the guard
> only answers "is a cycle reachable from here" on an already-exhausted stack. Run with `validate=True` (or call
> `container.validate()`) in development to surface *every* cycle (and other wiring bugs) before the first resolve,
> rather than only the one a particular resolve happens to hit.

### Inverted scope dependencies

For every dependency edge `provider → dep`, `validate()` compares their **effective scopes** (see below). If
`dep`'s effective scope is strictly deeper than `provider`'s effective scope, the dependency is inverted: a
shallower-lived provider cannot hold a reference to a deeper-lived one. The error is recorded as
`InvalidScopeDependencyError` (see `exceptions.py` for the exact message), which names the provider, the
parameter, the dependent provider, and the offending scopes. The walk continues into the dependency so further
issues in that subtree are also surfaced.

### Missing required dependencies

Before recursing into a provider's dependencies, `validate()` calls `provider.iter_validation_issues(container)`
and appends any returned exceptions to the error list. `Factory` implements this hook to yield
`ArgumentResolutionError` for each constructor parameter that has no matching provider in `providers_registry`,
no default value, and no static `kwargs` entry.

## Effective scope and alias transparency

`validate()`'s scope-ordering check uses `provider.effective_scope(container)` on both sides of every dependency
edge — not `provider.scope` directly.

For most providers, `effective_scope` simply returns `self.scope`. `Alias` overrides it to follow the alias chain
to its terminal non-alias target and return **that provider's scope**. This makes validation transitive through
aliases. Consider:

```
Factory(scope=APP, creator=Caller)   # depends on IFace
Alias(source_type=Impl, bound_type=IFace)  # no scope parameter
Factory(scope=REQUEST, creator=Impl)
```

The alias's effective scope is `REQUEST` (the scope of `Impl`). When `validate()` checks the `Caller → IFace`
edge, it compares `APP` against `REQUEST` and raises `InvalidScopeDependencyError`. Without `effective_scope`,
the alias's internal `scope` attribute (defaulting to `APP`) would mask the true depth of the dependency.

Two edge cases in `Alias.effective_scope` are handled safely:

- **Alias cycle**: if the same alias is encountered twice during the chain walk, the method falls back to
  `self.scope` and returns immediately. The cycle itself is separately detected and reported by the DFS cycle
  check.
- **Dangling source**: if the alias's source type is not registered, the method falls back to `self.scope`. The
  dangling source is separately detected and reported by `iter_validation_issues` or by the dependency lookup
  raising `AliasSourceNotRegisteredError` during the walk.

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
