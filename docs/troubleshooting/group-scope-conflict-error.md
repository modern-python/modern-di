# GroupScopeConflictError

## Symptom

```
modern_di.exceptions.registration.GroupScopeConflictError: Provider SomeService is shared by groups with conflicting default scopes: GroupA (scope REQUEST) and GroupB (scope ACTION). Set scope= explicitly on the provider, or align the group defaults.
See: https://modern-di.modern-python.org/troubleshooting/group-scope-conflict-error/
```

It is raised by the second group's `class` statement, usually at import time. The first group named
is the one that set the provider's scope. The exception carries `.provider`, `.first_group`,
`.first_scope`, `.second_group` and `.second_scope`.

## Cause

A provider declared without `scope=` takes its scope from the first `class ...(Group, scope=...)`
that lists it. When a second group with a different default scope lists the same provider instance,
the provider would need two scopes at once. Import order must not pick the winner, so `modern-di`
rejects the second group. This happens whether or not a container has registered the provider yet.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class SomeService: ...
-->

<!-- raises: GroupScopeConflictError -->

```python
# Broken:
shared = providers.Factory(SomeService)


class GroupA(Group, scope=Scope.REQUEST):
    svc = shared


class GroupB(Group, scope=Scope.ACTION):
    svc = shared
```

## Fix

Set `scope=` on the shared provider. An explicit scope always wins over a group default, so the two
groups no longer disagree:

```python
shared = providers.Factory(SomeService, scope=Scope.REQUEST)


class GroupA(Group, scope=Scope.REQUEST):
    svc = shared


class GroupB(Group, scope=Scope.ACTION):
    svc = shared


assert shared.scope == Scope.REQUEST
```

Or align the two groups' default scopes:

```python
shared = providers.Factory(SomeService)


class GroupA(Group, scope=Scope.REQUEST):
    svc = shared


class GroupB(Group, scope=Scope.REQUEST):
    svc = shared
```

In both of these, pass only one of the two groups to a given container. They list the same provider
instance, and `Container(groups=[GroupA, GroupB])` currently raises
[`DuplicateProviderTypeError`](duplicate-type-error.md) naming that one provider twice.

Or give each group its own provider instance. The two then need different types, or `bound_type=None`
on one, to avoid a [`DuplicateProviderTypeError`](duplicate-type-error.md) when both groups go into
one container:

```python
class GroupA(Group, scope=Scope.REQUEST):
    svc = providers.Factory(SomeService)


class GroupB(Group, scope=Scope.ACTION):
    svc = providers.Factory(SomeService, bound_type=None)


container = Container(groups=[GroupA, GroupB])
```

## See also

- [Scopes: group-level default scope](../providers/scopes.md#group-level-default-scope): how a provider's scope is chosen.
- [ProviderScopeFrozenError](provider-scope-frozen-error.md): a group changing the scope of an already registered provider.
