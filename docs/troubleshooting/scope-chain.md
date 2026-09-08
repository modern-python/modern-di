# Scope chain violation

This error fires when a provider depends on another provider at a deeper (shorter-lived) scope — see [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for why that's disallowed.

## Understanding the error

You'll see something like:

```
Container.validate() found 1 issue(s): InvalidScopeDependencyError

InvalidScopeDependencyError (1):
  - Provider at a deeper scope reached through this chain:
      APP      UserCache (myapp.providers:10)
      REQUEST  └─> Session (myapp.providers:4)
      caused by: UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
```

The fix is always to make the depender's scope equal to or shorter than the dependee's. In the example above, `UserCache` should be REQUEST-scoped, not APP-scoped.

The chain is the same arrow tree `ScopeNotInitializedError` and `ScopeSkippedError` draw at runtime, so the same violation reads identically whether you find it with `validate()` or by resolving.

### When the dependency is reached through an alias

An [`Alias`](../providers/alias.md) declares no scope of its own, so the type on the parameter is not the type that owns the offending scope. The chain names every hop and draws each one at the scope it actually resolves at:

```
InvalidScopeDependencyError (1):
  - Provider at a deeper scope reached through this chain:
      APP      UserCache (myapp.providers:10)
      REQUEST  └─> Repository
      REQUEST      └─> Session (myapp.providers:4)
      caused by: UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
```

`Repository` is the alias and `Session` is what supplies it. Programmatically, `.dep_provider` is the alias, `.dep_terminal` is the source, and `.dep_chain` is every hop between them.

## Common cases

1. **Forgot `scope=Scope.REQUEST` on a repository.** Defaults to `Scope.APP` if omitted. A repository that holds a session needs `scope=Scope.REQUEST`.
2. **Helper or utility provider auto-defaulted to APP.** Same as above — anything that consumes the session is REQUEST-scoped.
3. **Choice factory consuming the request.** A factory that depends on the framework's `Request` is REQUEST-scoped; you cannot resolve it from the APP container.

## How to fix

Bump the depender's scope:

```python
class Dependencies(Group):
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )

    # ❌ APP-scoped — fails validation
    user_repository = providers.Factory(UserRepository)

    # ✅ REQUEST-scoped — matches session's lifetime
    user_repository = providers.Factory(
        UserRepository,
        scope=Scope.REQUEST,
    )
```

## Detect early

`container.validate()` runs this check at startup, before the first request. Call it — the
diagnostic is much clearer than the runtime symptoms.

## See also

- [Scopes](../providers/scopes.md#the-scope-dependency-rule) — the lifetime model and the "max of dependencies' scopes" rule.
- [Lifecycle](../providers/lifecycle.md) — `container.validate()` and other startup checks.
