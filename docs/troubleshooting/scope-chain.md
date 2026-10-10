# Scope chain violation

This error fires when a provider depends on another provider at a deeper (shorter-lived) scope. See [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for why that's disallowed.

## Symptom

You'll see something like:

```
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 1 issue(s): InvalidScopeDependencyError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.registration.InvalidScopeDependencyError: Provider at a deeper scope reached through this chain:
    |   APP      UserCache (myapp.providers:10)
    |   REQUEST  └─> Session (myapp.providers:4)
    |   caused by: UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
    | See: https://modern-di.modern-python.org/troubleshooting/scope-chain/
    +------------------------------------
```

The fix is always to make the depender's scope equal to or shorter than the dependee's. In the example above, `UserCache` is APP-scoped and should be REQUEST-scoped.

The chain is the same arrow tree `ScopeNotInitializedError` and `ScopeSkippedError` draw at runtime, so the same violation reads identically whether you find it with `validate()` or by resolving.

### When the dependency is reached through an alias

An [`Alias`](../providers/alias.md) declares no scope of its own, so the type on the parameter is not the type that owns the offending scope. The chain names every hop and draws each one at the scope it actually resolves at:

```
modern_di.exceptions.registration.InvalidScopeDependencyError: Provider at a deeper scope reached through this chain:
  APP      UserCache (myapp.providers:10)
  REQUEST  └─> Repository
  REQUEST      └─> Session (myapp.providers:4)
  caused by: UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
See: https://modern-di.modern-python.org/troubleshooting/scope-chain/
```

`Repository` is the alias and `Session` is what supplies it. Programmatically, `.dependency_provider` is the alias, `.dependency_terminal` is the source, and `.dependency_chain` is every hop between them.

## Cause

1. A repository is missing `scope=Scope.REQUEST`. The scope defaults to `Scope.APP` if omitted, and a repository that holds a session needs `scope=Scope.REQUEST`.
2. A helper or utility provider auto-defaulted to APP. As above, anything that consumes the session is REQUEST-scoped.
3. A choice factory consumes the request. A factory that depends on the framework's `Request` is REQUEST-scoped; you cannot resolve it from the APP container.

## How to detect

`container.validate()` runs this check at startup, before the first request. Call it: the
diagnostic is much clearer than the runtime symptoms.

## Fix

Bump the depender's scope:

<!-- invisible-code-block: python
from modern_di import Group, Scope, providers


class Session: ...


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session


def create_session() -> Session:
    return Session()


def close_session(session: Session) -> None: ...
-->

```python
class Dependencies(Group):
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )

    # Broken: APP-scoped, fails validation
    user_repository = providers.Factory(UserRepository)

    # Works: REQUEST-scoped, matches session's lifetime
    user_repository = providers.Factory(
        UserRepository,
        scope=Scope.REQUEST,
    )
```

## See also

- [Scopes](../providers/scopes.md#the-scope-dependency-rule) explains the lifetime model and the "max of dependencies' scopes" rule.
- [Lifecycle](../providers/lifecycle.md) covers `container.validate()` and other startup checks.
