# UnknownFactoryKwargError

**Symptom**

Raised at `Factory(...)` declaration time, listing the `kwargs` key(s) that don't match the creator's
signature, the known parameter names, and a "did you mean" suggestion when a close match exists.

**Cause**

A key in `kwargs={...}` doesn't correspond to any parameter of the creator — usually a typo, or a key
left over after the creator's signature was renamed/refactored. The creator has no `**kwargs`
catch-all, so `modern-di` can validate the keys eagerly at declaration time rather than only failing
at call time.

**Fix**

Match the `kwargs` keys to the creator's actual parameter names:

```python
def create_service(connection_string: str) -> Service: ...


class Dependencies(Group):
    # Wrong: typo — raises UnknownFactoryKwargError, suggests "connection_string"
    service = providers.Factory(
        create_service, scope=Scope.APP, kwargs={"conection_string": "..."}
    )

    # Right
    service = providers.Factory(
        create_service, scope=Scope.APP, kwargs={"connection_string": "..."}
    )
```

If the creator genuinely accepts arbitrary keyword arguments (`**kwargs` in its signature), this check
is skipped automatically — no escape hatch needed.

## See also

- [Factories: kwargs](../providers/factories.md#kwargs).
