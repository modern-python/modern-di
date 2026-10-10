# ScopeNotInitializedError

## Symptom

`resolve()` or `resolve_provider()` raises it when a provider's scope is deeper than the container
that has to build it. Resolving a `REQUEST`-scoped provider from the `APP` container prints:

```text
modern_di.exceptions.container.ScopeNotInitializedError: Cannot resolve dependency chain:
  REQUEST  Session (myapp.providers:7)
  caused by: Provider of scope REQUEST cannot be resolved in container of scope APP.
See: https://modern-di.modern-python.org/troubleshooting/scope-not-initialized-error/
```

When a shallower provider depends on the deeper one, the chain starts at the shallower provider:

```text
modern_di.exceptions.container.ScopeNotInitializedError: Cannot resolve dependency chain:
  APP      UserCache (myapp.providers:10)
  REQUEST  └─> Session (myapp.providers:7)
  caused by: Provider of scope REQUEST cannot be resolved in container of scope APP.
See: https://modern-di.modern-python.org/troubleshooting/scope-not-initialized-error/
```

Each chain line names a provider's scope and type and, when it can be found, the `module:line` where
its creator is defined (the class or function, not the `Factory(...)` line). `.provider_scope` and
`.container_scope` hold the two scopes in the `caused by` line.

## Cause

The container that has to build the provider is shallower than the provider's scope, in one of two
ways:

- You resolved a provider from a container shallower than the provider's scope, and no container at
  that scope exists below it yet. The first sample is `container.resolve(Session)` on the `APP`
  container, with no `REQUEST` child built.
- A provider depends on a deeper-scoped one, a captive dependency. An `APP`-scoped `UserCache` is
  built in the `APP` container even when you call `resolve(UserCache)` on a `REQUEST` child, and the
  `APP` container cannot build the `REQUEST`-scoped `Session` it needs. That is why the second sample
  names container scope `APP` although the call went to a `REQUEST` container.

## Fix

In the first case, build the deeper container and resolve from it:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Session: ...


class Dependencies(Group):
    session = providers.Factory(Session, scope=Scope.REQUEST)


app_container = Container(groups=[Dependencies])
-->

<!-- raises: ScopeNotInitializedError -->

```python
# Broken: no REQUEST container exists yet
app_container.resolve(Session)
```

```python
# Works
request_container = app_container.build_child_container(scope=Scope.REQUEST)
request_container.resolve(Session)
```

In the captive case a deeper container does not help. Move the depending provider to the deeper
scope, or give the dependency a shallower scope if its lifetime allows. `container.validate()` finds
every captive dependency at startup and reports it as
[`InvalidScopeDependencyError`](scope-chain.md), whose page shows both fixes.

## See also

- [InvalidScopeDependencyError](scope-chain.md) — the same problem reported by `validate()`.
- [Scopes: the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) — why a
  provider cannot depend on a deeper scope.
- [Captive dependency](../recipes/good-and-bad-practices.md#1-captive-dependency-a-wide-scoped-provider-holding-a-narrow-scoped-one)
  — the bug this error usually points at.
