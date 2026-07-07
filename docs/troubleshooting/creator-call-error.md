# CreatorCallError

**Symptom**

Raised naming the creator that could not be called and the underlying `TypeError`, with a pointer to
check `kwargs` and `skip_creator_parsing` usage.

**Cause**

Argument binding failed when calling the creator: the set of arguments `modern-di` assembled (static
`kwargs` plus resolved dependencies) doesn't match the creator's signature — a required argument is
missing, or an unexpected one was passed. This typically happens with `skip_creator_parsing=True`
(where every required argument must be covered by `kwargs`) or a `kwargs` dict that drifted from the
signature. This is a **wiring problem, not a bug inside your constructor** — an exception raised
inside the creator's body (even a `TypeError`) propagates unchanged as itself, never wrapped in this
error.

**Fix**

Make `kwargs` cover exactly what the signature requires. `.original_error` (also the `__cause__`)
holds the binding `TypeError` naming the mismatched argument:

```python
def create_service(host: str, port: int) -> Service: ...


class Dependencies(Group):
    # Wrong: skip_creator_parsing=True but kwargs misses `port`
    service = providers.Factory(
        scope=Scope.APP, creator=create_service, skip_creator_parsing=True,
        bound_type=Service, kwargs={"host": "localhost"},
    )

    # Right
    service = providers.Factory(
        scope=Scope.APP, creator=create_service, skip_creator_parsing=True,
        bound_type=Service, kwargs={"host": "localhost", "port": 5432},
    )
```

Without `skip_creator_parsing`, unknown `kwargs` keys are caught earlier, at declaration time — see
the page below.

## See also

- [Unknown factory kwarg](unknown-factory-kwarg-error.md) — the declaration-time form of a kwargs mismatch.
- [Factories: skip_creator_parsing](../providers/factories.md#skip_creator_parsing).
