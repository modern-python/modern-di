# ScopeEnumMismatchError

## Symptom

`container.validate()` raises `ValidationFailedError`, and one of its `.exceptions` is a
`ScopeEnumMismatchError`:

```
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 1 issue(s): ScopeEnumMismatchError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.registration.ScopeEnumMismatchError: Provider at a same-valued scope of another enum reached through this chain:
    |   SESSION  UserSession (myapp.providers:15)
    |   TENANT   └─> TenantSettings (myapp.providers:11)
    |   caused by: UserSession (scope Scope.SESSION) declares parameter 'settings' typed as a provider of TenantSettings at scope Tenancy.TENANT. Both scopes have the value 2 but belong to different enums, so they can never be in one container chain. Give the dependency the same scope member as UserSession or a shallower one.
    | See: https://modern-di.modern-python.org/troubleshooting/scope-enum-mismatch-error/
    +------------------------------------
```

## Cause

A provider matches its container by enum member. Scopes from different enums can share a value,
like `Scope.SESSION` and `Tenancy.TENANT` here, which are both 2. A container chain holds at most
one container per value, because each child's value is higher than its parent's. The `SESSION`
container is the one at value 2, so no `TENANT` container can exist in its chain, and
`UserSession` can never resolve its `settings` dependency. Resolving it raises
`ScopeSkippedError`.

A dependency on a *shallower* scope from another enum is fine. A `Scope.REQUEST` provider can depend
on a `Tenancy.TENANT` provider when the chain is built `APP → TENANT → REQUEST`.

## Fix

Give the dependency the same scope member as the provider that needs it, or a shallower one:

<!-- skip: next "fragment" -->

```python
class Tenancy(IntEnum):
    TENANT = 2


class Dependencies(Group):
    # Broken: TENANT and SESSION are both 2
    settings = providers.Factory(TenantSettings, scope=Tenancy.TENANT)
    session = providers.Factory(UserSession, scope=Scope.SESSION)

    # Works: the dependency is shallower than the provider
    settings = providers.Factory(TenantSettings, scope=Scope.APP)
    session = providers.Factory(UserSession, scope=Scope.SESSION)
```

Inspect `.provider`, `.parameter_name` and `.dependency_chain` on the exception.
`.dependency_provider` and `.dependency_terminal` are the ends of the chain; they differ when the
dependency is reached through an `Alias`.

## See also

- [Scopes](../providers/scopes.md#custom-scopes) explains how scopes from different enums mix in one tree.
- [Scope chain violation](scope-chain.md) covers a dependency on a deeper scope.
