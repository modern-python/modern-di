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
See the [migration guide](../docs/migration/to-3.x.md) for the full readiness recipe.

## What validate() checks

`validate()` performs a depth-first search (DFS) over every provider in `providers_registry`. It collects **all
errors** across the entire walk before raising, so a single call surfaces all wiring bugs at once rather than
stopping at the first one.

If any errors are found, `validate()` raises `exceptions.ValidationFailedError`, whose `.errors` attribute is a
list of all individual exceptions encountered. `ValidationFailedError.__str__` groups `.errors` by exception
class name (sorted alphabetically) so a report mixing several error kinds reads as one section per kind rather
than an undifferentiated flat list — see [Report rendering](#report-rendering) below for the exact shape.

### Circular dependencies

During the DFS, a provider encountered a second time while it is still on the active path (i.e., it appears in
`visiting`) means a cycle exists. `validate()` records a `CircularDependencyError` with a `.cycle_path` list of
type names showing the loop (e.g., `["A", "B", "A"]`). The recursive walk does **not** continue into the cycle,
but the rest of the graph continues to be checked.

`CircularDependencyError.__str__` renders `.cycle_path` as a multi-line arrow chain (the same `└─>` continuation
style as the `ResolutionError` dependency-chain breadcrumb), not an inline `A -> B -> A` string:

```
Circular dependency detected:
  A
  └─> B
      └─> A
Check your provider graph for unintended cycles.
```

> **Runtime resolution has no cycle guard.** Cycle detection lives only here. To keep the resolve hot path free of
> per-resolve bookkeeping, `resolve()` does not track in-flight providers — a circular graph that is never validated
> raises a raw `RecursionError` on first resolve. Run with `validate=True` (or call `container.validate()`) in
> development to surface cycles as a clear `CircularDependencyError` instead.

### Inverted scope dependencies

For every dependency edge `provider → dep`, `validate()` compares their **effective scopes** (see below). If
`dep`'s effective scope is strictly deeper than `provider`'s effective scope, the dependency is inverted: a
shallower-lived provider cannot hold a reference to a deeper-lived one. The error is recorded as
`InvalidScopeDependencyError`, which names the provider, the parameter, the dependent provider, and the offending
scopes. The walk continues into the dependency so further issues in that subtree are also surfaced.

Error message template (from `errors.INVALID_SCOPE_DEPENDENCY_ERROR`):

```
Provider {provider_name} (scope {provider_scope}) declares parameter
{parameter_name!r} typed as a provider of {dep_name} at deeper scope
{dep_scope}. A provider cannot depend on a deeper-scoped provider.
```

### Missing required dependencies

Before recursing into a provider's dependencies, `validate()` calls `provider.iter_validation_issues(container)`
and appends any returned exceptions to the error list. `Factory` implements this hook to yield
`ArgumentResolutionError` for each constructor parameter that has no matching provider in `providers_registry`,
no default value, and no static `kwargs` entry.

### Report rendering

`ValidationFailedError.__str__` starts with the one-line summary (`Container.validate() found N issue(s): ...`,
used by `repr`/logging), then one section per exception class, sorted by class name, each headed
`{ClassName} ({count}):` and listing its errors as `  - ` bullets. An error's own multi-line message (e.g. a
`CircularDependencyError` arrow chain, or a `ProviderNotRegisteredError`'s "Did you mean" suggestion block) has
its first line placed after the bullet and every continuation line indented four spaces so multi-line
sub-errors read as a block rather than mangling into the bullet list. A trailing blank message line is stripped
(the `rstrip`/empty-message guard), so an error with no extra content renders as a bare `  - ` without a dangling
space.

A container with both a circular dependency and a missing provider renders as:

```
Container.validate() found 2 issue(s): CircularDependencyError, ProviderNotRegisteredError

CircularDependencyError (1):
  - Circular dependency detected:
      A
      └─> B
          └─> A
    Check your provider graph for unintended cycles.

ProviderNotRegisteredError (1):
  - Provider of type <class 'str'> is not registered in providers registry.
    Did you mean:
    Str2
```

## Effective scope and alias transparency

`validate()`'s scope-ordering check uses `provider.effective_scope(container)` on both sides of every dependency
edge — not `provider.scope` directly.

For most providers, `effective_scope` simply returns `self.scope`. `Alias` overrides it to follow the alias chain
to its terminal non-alias target and return **that provider's scope**:

```
Alias.effective_scope(container)
  → follow chain: Alias → Alias → ... → concrete Factory
  → return concrete_factory.scope
```

This makes validation transitive through aliases. Consider:

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

## The deprecated `Alias(scope=...)` parameter

`Alias` accepts a `scope` keyword argument that was historically intended to convey the alias's position in the
scope hierarchy. Because an alias is a transparent redirect — resolution always delegates to the source, and (as
of the `effective_scope` mechanism) validation now evaluates the source's scope transitively — the `scope`
parameter has no effect on either behavior.

Passing `scope=` to `Alias` now emits a `DeprecationWarning`:

```
The `scope` parameter of Alias is deprecated and ignored: an alias's effective
scope is derived from its source. It will be removed in a future release.
```

The stored value is kept internally only so that cosmetic consumers (`__repr__`, registry suggestions) continue
to display it. The parameter is scheduled for removal in a future release. New code should omit it.

## DFS algorithm summary

```
validate():
  visiting = set()   # providers currently on the active path
  visited  = set()   # providers fully processed
  path     = list()  # ordered active path (for cycle reporting)
  errors   = list()

  for each provider in providers_registry:
      _visit(provider)

  if errors:
      raise ValidationFailedError(errors=errors)

_visit(provider):
  if provider in visited:  return        # already processed; skip
  if provider in visiting:               # back-edge → cycle
      record CircularDependencyError
      return                             # don't recurse into the cycle

  mark visiting; append to path
  errors.extend(provider.iter_validation_issues(container))

  provider_scope = provider.effective_scope(container)
  for dep_name, dep_provider in provider.get_dependencies(container):
      dep_scope = dep_provider.effective_scope(container)
      if dep_scope > provider_scope:
          record InvalidScopeDependencyError
      _visit(dep_provider)               # recurse regardless of scope error

  remove from path; unmark visiting; mark visited
```

`provider.get_dependencies(container)` is a pure registry lookup — it does not touch `cache_registry`, does not
call `find_container`, and does not perform any runtime context check. This means `validate()` works correctly on
a root APP-scope container even when the graph contains SESSION-, REQUEST-, ACTION-, or STEP-scoped providers.

## Exception types

| Exception | Base | Raised by |
|---|---|---|
| `ValidationFailedError` | `ContainerError` | `Container.validate()` — aggregate wrapper |
| `CircularDependencyError` | `ResolutionError` | recorded inside `validate()` on cycle detection |
| `InvalidScopeDependencyError` | `RegistrationError` | recorded inside `validate()` on inverted scope edge |
| `ArgumentResolutionError` | `ResolutionError` | yielded by `Factory.iter_validation_issues()` |
