# ScopeSkippedError

## Symptom

`resolve()` or `resolve_provider()` raises it when a provider's scope is shallower than the container
you resolve from, but no container at that scope exists in the chain. The message has two forms. When
the chain skipped an intermediate scope:

```text
modern_di.exceptions.container.ScopeSkippedError: Cannot resolve dependency chain:
  REQUEST  Session (myapp.providers:7)
  caused by: No REQUEST-scope container exists in this chain, which runs from APP to ACTION. Add a container at scope REQUEST to the chain.
See: https://modern-di.modern-python.org/troubleshooting/scope-skipped-error/
```

When the root container is deeper than the provider:

```text
modern_di.exceptions.container.ScopeSkippedError: Cannot resolve dependency chain:
  APP  Settings (myapp.providers:4)
  caused by: No APP-scope container exists in this chain, which starts at SESSION. Build the root container at scope APP.
See: https://modern-di.modern-python.org/troubleshooting/scope-skipped-error/
```

Each chain line names a provider's scope and type and, when it can be found, the `module:line` where
its creator is defined. `.provider_scope` is the scope with no container, `.container_scope` the
container you resolved from, and `.root_scope` the root of its chain.

## Cause

The chain has no container at the provider's scope, for one of three reasons:

- The chain skipped an intermediate scope when it was built. A chain built `APP → ACTION` has no
  `REQUEST` container for a `REQUEST`-scoped provider, even though `REQUEST` is shallower than
  `ACTION`.
- The root container is deeper than the provider's scope. A chain whose root is a `SESSION`
  container has no `APP` container, so an `APP`-scoped provider cannot resolve anywhere in it.
- The provider's scope comes from a different enum than the chain's containers. A provider resolves
  only in a container built at the same enum member, so a provider at `Scope.APP` does not resolve in
  a container at `AppScope.APP` from your own enum. The message then names the same scope twice, as
  in `No APP-scope container exists in this chain, which starts at APP.`, because both members are
  named `APP`. A provider that depends on another at a same-valued member of a different enum is
  reported by `validate()` as [`ScopeEnumMismatchError`](scope-enum-mismatch-error.md).

## Fix

Build a child container at every scope your providers use:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Settings: ...


class Session: ...


class Dependencies(Group):
    settings = providers.Factory(Settings)
    session = providers.Factory(Session, scope=Scope.REQUEST)


app_container = Container(groups=[Dependencies])
-->

<!-- raises: ScopeSkippedError -->

```python
# Broken: the chain jumps from APP straight to ACTION
action_container = app_container.build_child_container(scope=Scope.ACTION)
action_container.resolve(Session)
```

```python
# Works: build through REQUEST first
request_container = app_container.build_child_container(scope=Scope.REQUEST)
action_container = request_container.build_child_container(scope=Scope.ACTION)
action_container.resolve(Session)
```

When the root is too deep, build the root at the provider's scope and derive the deeper containers
from it:

<!-- raises: ScopeSkippedError -->

```python
# Broken: the chain starts at SESSION, so there is no APP container
session_container = Container(scope=Scope.SESSION, groups=[Dependencies])
request_container = session_container.build_child_container(scope=Scope.REQUEST)
request_container.resolve(Settings)
```

```python
# Works: the root is the APP container
app_container = Container(scope=Scope.APP, groups=[Dependencies])
session_container = app_container.build_child_container(scope=Scope.SESSION)
request_container = session_container.build_child_container(scope=Scope.REQUEST)
request_container.resolve(Settings)
```

When the provider's scope comes from another enum, declare it at a member of the enum the containers
use.

If a framework integration builds the chain for you, check which scopes it builds for each request or
message, and give your providers those scopes.

## See also

- [InvalidScopeDependencyError](scope-chain.md) — a provider that depends on a deeper scope, found by
  `validate()`.
- [Scopes: building child containers](../providers/scopes.md#building-child-containers) — how a
  container chain maps to the scope hierarchy.
