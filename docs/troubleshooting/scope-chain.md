# Scope chain violation

This error fires when a provider depends on another provider with a *shorter* lifetime than its own. APP-scoped factories cannot consume REQUEST-scoped dependencies, because the REQUEST instance would outlive its request.

## Understanding the error

You'll see something like:

```
RuntimeError: Provider <APP-scope UserCache> depends on <REQUEST-scope AsyncSession>
which has a shorter lifetime. A shorter-lived dependency would be captured by a
longer-lived one and become stale across requests.
```

The fix is always to make the depender's scope equal to or shorter than the dependee's. In the example above, `UserCache` should be REQUEST-scoped, not APP-scoped.

## Common cases

1. **Forgot `scope=Scope.REQUEST` on a repository.** Defaults to `Scope.APP` if omitted. A repository that holds a session needs `scope=Scope.REQUEST`.
2. **Helper or utility provider auto-defaulted to APP.** Same as above — anything that consumes the session is REQUEST-scoped.
3. **Choice factory consuming the request.** A factory that depends on the framework's `Request` is REQUEST-scoped; you cannot resolve it from the APP container.

## How to fix

Bump the depender's scope:

```python
class Dependencies(Group):
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache_settings=providers.CacheSettings(finalizer=close_session),
    )

    # ❌ APP-scoped — fails validation
    user_repository = providers.Factory(creator=UserRepository)

    # ✅ REQUEST-scoped — matches session's lifetime
    user_repository = providers.Factory(
        scope=Scope.REQUEST,
        creator=UserRepository,
    )
```

## Detect early

`Container(groups=[...], validate=True)` runs this check at startup, before the first request. Always pass `validate=True` — the diagnostic is much clearer than the runtime symptoms.

## See also

- [Scopes](../providers/scopes.md) — the lifetime model and the "max of dependencies' scopes" rule.
- [Lifecycle](../providers/lifecycle.md) — `validate=True` and other startup checks.
