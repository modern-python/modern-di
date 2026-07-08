# Scope chain violation

This error fires when a provider depends on another provider at a deeper (shorter-lived) scope — see [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for why that's disallowed.

## Understanding the error

You'll see something like:

```
Container.validate() found 1 issue(s): InvalidScopeDependencyError

InvalidScopeDependencyError (1):
  - Provider UserCache (scope APP) declares parameter 'session' typed as a provider of Session at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
```

The fix is always to make the depender's scope equal to or shorter than the dependee's. In the example above, `UserCache` should be REQUEST-scoped, not APP-scoped.

This particular message is a single static check with no chain attached; if the same violation instead surfaces at runtime as `ScopeNotInitializedError` or `ScopeSkippedError`, their breadcrumb lines may end with a pointer to where the offending provider was declared (module and line number).

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

`Container(groups=[...], validate=True)` runs this check at startup, before the first request. Always pass `validate=True` — the diagnostic is much clearer than the runtime symptoms.

## See also

- [Scopes](../providers/scopes.md#the-scope-dependency-rule) — the lifetime model and the "max of dependencies' scopes" rule.
- [Lifecycle](../providers/lifecycle.md) — `validate=True` and other startup checks.
