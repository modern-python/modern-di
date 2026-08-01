# ProviderScopeFrozenError

**Symptom**

Defining a `Group` subclass raises at class-creation (import) time. The error names a provider, the
group that tried to change its scope, and the two scopes involved — and says the provider is
already registered with a container.

**Cause**

A provider created without an explicit `scope=` takes its scope from whichever
`class ...(Group, scope=...)` body stamps it first. A group declared **without** a `scope=` kwarg
stamps nothing, so a provider listed only in such a group keeps the `Scope.APP` default and stays
unclaimed — a later group is still free to stamp it.

That is fine until the provider has been registered with a container. Registration compiles a
resolver for the provider, and that resolver **captures the scope as it was at compile time**.
Changing the scope afterwards would apply only to resolvers compiled later, so the same provider
would resolve one way through the existing container and another way through a fresh one. Rather
than let the two disagree silently, the scope is frozen at registration and the change is rejected.

```python
shared = providers.Factory(SomeService)          # no explicit scope -> APP default, unclaimed

class PlainGroup(Group):                          # no scope= -> stamps nothing
    svc = shared

container = Container(scope=Scope.APP, groups=[PlainGroup])   # registers + compiles

class ScopedGroup(Group, scope=Scope.REQUEST):    # ProviderScopeFrozenError
    svc = shared
```

**Fix**

```python
# 1. Set scope= explicitly on the provider — explicit always wins over a group default,
#    and the provider is never left unclaimed in the first place.
shared = providers.Factory(SomeService, scope=Scope.REQUEST)

# 2. Declare every group that lists the provider before building the container.
class PlainGroup(Group):
    svc = shared

class ScopedGroup(Group, scope=Scope.REQUEST):
    svc = shared

container = Container(scope=Scope.APP, groups=[ScopedGroup])   # now consistent

# 3. Give the scoped group its own provider instance instead of sharing one.
class ScopedGroup(Group, scope=Scope.REQUEST):
    svc = providers.Factory(SomeService)
```

Inspect `.provider_name`, `.group_name`, `.current_scope`, and `.new_scope` on the exception to see
exactly which provider and group collided.

Note the difference from
[`GroupScopeConflictError`](group-scope-conflict-error.md): that one fires when two groups *both*
declare a scope and disagree, whether or not anything is registered. This one fires when a single
group would change the scope of a provider that a container has already compiled.

## See also

- [Scopes](../providers/scopes.md) — the scope hierarchy and how a provider's scope is chosen.
- [GroupScopeConflictError](group-scope-conflict-error.md) — two groups disagreeing about a scope.
