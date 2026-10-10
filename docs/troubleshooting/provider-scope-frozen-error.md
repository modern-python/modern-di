# ProviderScopeFrozenError

## Symptom

```
modern_di.exceptions.registration.ProviderScopeFrozenError: Group ScopedGroup would change the scope of provider SomeService from APP to REQUEST, but it is already registered with a container. Resolvers compiled before this point captured APP, so the change would apply inconsistently. Declare ScopedGroup before building the container, or set scope= explicitly on the provider.
See: https://modern-di.modern-python.org/troubleshooting/provider-scope-frozen-error/
```

It is raised by the group's `class` statement. The exception carries `.provider`, `.group_name`,
`.current_scope` and `.new_scope`.

## Cause

A provider created without an explicit `scope=` takes its scope from whichever
`class ...(Group, scope=...)` body stamps it first. A group declared without a `scope=` kwarg
stamps nothing, so a provider listed only in such a group keeps the `Scope.APP` default and stays
unclaimed, which leaves a later group free to stamp it.

That is fine until the provider has been registered with a container. Registration compiles a
resolver for the provider, and that resolver captures the scope as it was at compile time.
Changing the scope afterwards would apply only to resolvers compiled later, so the same provider
would resolve one way through the existing container and another way through a fresh one. To keep
the two from disagreeing silently, the scope is frozen at registration and the change is rejected.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class SomeService: ...
-->

<!-- raises: ProviderScopeFrozenError -->

```python
# Broken:
shared = providers.Factory(SomeService)


class PlainGroup(Group):
    svc = shared


container = Container(scope=Scope.APP, groups=[PlainGroup])


class ScopedGroup(Group, scope=Scope.REQUEST):
    svc = shared
```

[`GroupScopeConflictError`](group-scope-conflict-error.md) is the related case where two groups both
declare a scope and disagree, whether or not anything is registered. This error fires when a single
group would change the scope of a provider that a container has already compiled.

## Fix

Set `scope=` on the provider. An explicit scope always wins over a group default, so no group ever
changes it:

```python
shared = providers.Factory(SomeService, scope=Scope.REQUEST)


class PlainGroup(Group):
    svc = shared


container = Container(scope=Scope.APP, groups=[PlainGroup])


class ScopedGroup(Group, scope=Scope.REQUEST):
    svc = shared
```

Or declare every group that lists the provider before building the container:

```python
shared = providers.Factory(SomeService)


class PlainGroup(Group):
    svc = shared


class ScopedGroup(Group, scope=Scope.REQUEST):
    svc = shared


container = Container(scope=Scope.APP, groups=[ScopedGroup])
assert shared.scope == Scope.REQUEST
```

Pass only one of the two groups to a given container. Both list the same provider instance, and
`Container(groups=[PlainGroup, ScopedGroup])` currently raises
[`DuplicateProviderTypeError`](duplicate-type-error.md) naming that one provider twice.

Or give the scoped group its own provider instance instead of sharing one:

```python
shared = providers.Factory(SomeService)


class PlainGroup(Group):
    svc = shared


container = Container(scope=Scope.APP, groups=[PlainGroup])


class ScopedGroup(Group, scope=Scope.REQUEST):
    svc = providers.Factory(SomeService)
```

## See also

- [Scopes: group-level default scope](../providers/scopes.md#group-level-default-scope): how a provider's scope is chosen.
- [GroupScopeConflictError](group-scope-conflict-error.md): two groups disagreeing about a provider's scope.
