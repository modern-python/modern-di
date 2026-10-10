# InvalidScopeDependencyError

## Symptom

`container.validate()` raises `ValidationFailedError`, and one of its `.exceptions` is an
`InvalidScopeDependencyError`:

```text
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 1 issue(s): InvalidScopeDependencyError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.registration.InvalidScopeDependencyError: Provider at a deeper scope reached through this chain:
    |   APP      UserCache (myapp.providers:10)
    |   REQUEST  └─> Session (myapp.providers:7)
    |   caused by: UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
    | See: https://modern-di.modern-python.org/troubleshooting/scope-chain/
    +------------------------------------
```

The chain runs from the provider that breaks the rule to the dependency it should not hold. Each
line names a scope, a type and, when it can be found, the `module:line` where the creator is
defined. Without `validate()`, resolving `UserCache` raises
[`ScopeNotInitializedError`](scope-not-initialized-error.md) instead. Its chain lines are the same,
but it starts with `Cannot resolve dependency chain:` and its `caused by` line names the container
that could not build `Session`.

Inspect `.provider` and `.parameter_name` for the depender and its parameter, and
`.dependency_chain` for the hops to the dependency.

### When the dependency is reached through an alias

An [`Alias`](../providers/alias.md) declares no scope of its own, so the type on the parameter is not the type that owns the offending scope. The chain names every hop and draws each one at the scope it actually resolves at:

```text
modern_di.exceptions.registration.InvalidScopeDependencyError: Provider at a deeper scope reached through this chain:
  APP      UserCache (myapp.providers:10)
  REQUEST  └─> Repository
  REQUEST      └─> Session (myapp.providers:7)
  caused by: UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
See: https://modern-di.modern-python.org/troubleshooting/scope-chain/
```

`Repository` is the alias and `Session` is what supplies it. Programmatically, `.dependency_provider` is the alias, `.dependency_terminal` is the source, and `.dependency_chain` is every hop between them.

## Cause

A provider depends on another provider at a deeper, shorter-lived scope. If it were built, a
long-lived object would hold a short-lived one past the end of its scope, so
[the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) forbids it. The
depender usually ends up at the wrong scope in one of these ways:

- Its `scope=` was left out, so it took the default: `Scope.APP`, or its group's default scope.
- It takes a per-request object, such as the framework's `Request`, which the integrations provide at
  `REQUEST` scope.

## Fix

Give the depender the dependency's scope or a deeper one. Call `validate()` at startup to find every
case before the first request.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Session: ...


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session


def create_session() -> Session:
    return Session()


def close_session(session: Session) -> None: ...
-->

<!-- raises: ValidationFailedError -->

```python
# Broken: UserRepository defaults to APP and needs the REQUEST-scoped session
class BrokenDependencies(Group):
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )
    user_repository = providers.Factory(UserRepository)


Container(groups=[BrokenDependencies]).validate()
```

```python
# Works: UserRepository lives as long as the session
class Dependencies(Group):
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )
    user_repository = providers.Factory(UserRepository, scope=Scope.REQUEST)


Container(groups=[Dependencies]).validate()
```

When the dependency does not need its shorter lifetime, the other fix is to give it the depender's
scope or a shallower one.

## See also

- [Scopes: how to choose a scope](../providers/scopes.md#how-to-choose-a-scope) — the shallowest
  scope a provider can have, given its dependencies.
- [Captive dependency](../recipes/good-and-bad-practices.md#1-captive-dependency-a-wide-scoped-provider-holding-a-narrow-scoped-one)
  — the mistake this error reports, and its fix.
- [Lifecycle: validation](../providers/lifecycle.md#validation) — when to call `validate()` and what
  it checks.
