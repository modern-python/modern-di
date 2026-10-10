# ScopeSkippedError

## Symptom

A resolution fails naming a provider's scope and where the container chain starts, optionally with
a dependency-path breadcrumb: the requested scope is shallower than the current container, but no
container at that scope exists anywhere in this chain. Each breadcrumb line may end with a pointer
to where that provider was declared (module and line number), so you can jump straight to the
declaration. The exception carries `.provider_scope`, `.container_scope` (the resolving container)
and `.root_scope` (the root of its chain).

## Cause

The chain has no container at the provider's scope, for one of two reasons:

- The chain skipped an intermediate scope when it was built. A chain built `APP → ACTION` (skipping
  `SESSION` and `REQUEST`) has no `REQUEST` container to satisfy a `REQUEST`-scoped provider, even
  though `REQUEST` is shallower than the current `ACTION` container. The message says
  "Add a container at scope REQUEST to the chain."
- The root container is deeper than the provider's scope. A chain whose root is a `SESSION`
  container has no `APP` container, so an `APP`-scoped provider cannot resolve anywhere in it. The
  message says "Build the root container at scope APP."

## Fix

Build child containers through every intermediate scope your providers need:

<!-- skip: next "fragment" -->

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup])

# Broken: jumps straight past REQUEST
action_container = app_container.build_child_container(scope=Scope.ACTION)
action_container.resolve(RequestScopedThing)  # raises ScopeSkippedError

# Works: build through REQUEST first
request_container = app_container.build_child_container(scope=Scope.REQUEST)
action_container = request_container.build_child_container(scope=Scope.ACTION)
action_container.resolve(RequestScopedThing)
```

When the root is too deep, build the root at the provider's scope and derive the deeper containers
from it:

<!-- skip: next "fragment" -->

```python
# Broken: the chain starts at SESSION, so there is no APP container
session_container = Container(scope=Scope.SESSION, groups=[MyGroup])
request_container = session_container.build_child_container(scope=Scope.REQUEST)
request_container.resolve(AppScopedThing)  # raises ScopeSkippedError

# Works: the root is the APP container
app_container = Container(scope=Scope.APP, groups=[MyGroup])
session_container = app_container.build_child_container(scope=Scope.SESSION)
request_container = session_container.build_child_container(scope=Scope.REQUEST)
request_container.resolve(AppScopedThing)
```

If a framework integration builds the chain for you, check which scopes it actually instantiates per
request/message and align your providers to those, not to the full built-in hierarchy.

## See also

- [Scope chain violation](scope-chain.md) covers the related, statically-detected form of this problem.
- [Scopes](../providers/scopes.md) explains how container chains map to the scope hierarchy.
