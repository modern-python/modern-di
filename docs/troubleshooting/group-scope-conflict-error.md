# GroupScopeConflictError

**Symptom**

Defining a `Group` subclass raises at class-creation (import) time. The error names a provider
and the two groups that disagree about its scope.

**Cause**

A module-level provider instance was created without an explicit `scope=`, so it takes its scope
from whichever `class ...(Group, scope=...)` body stamps it first. When that same instance is
also referenced from a second group whose default scope differs, the two stamps conflict — the
provider cannot have two different scopes, and import order must never be what silently decides
which one wins.

**Fix**

Three ways to resolve it, pick whichever fits:

```python
# 1. Set scope= explicitly on the shared provider — explicit always wins over a group default.
shared = providers.Factory(SomeService, scope=Scope.REQUEST)

# 2. Align the two groups' default scopes so they agree.
class GroupA(Group, scope=Scope.REQUEST):
    svc = shared

class GroupB(Group, scope=Scope.REQUEST):
    svc = shared

# 3. Give each group its own provider instance instead of sharing one.
class GroupA(Group, scope=Scope.REQUEST):
    svc = providers.Factory(SomeService)

class GroupB(Group, scope=Scope.ACTION):
    svc = providers.Factory(SomeService)
```

Inspect `.provider_name`, `.first_group`/`.first_scope`, and `.second_group`/`.second_scope` on
the exception to see exactly which provider and groups collided.

## See also

- [Scopes](../providers/scopes.md) — the scope hierarchy and how a provider's scope is chosen.
