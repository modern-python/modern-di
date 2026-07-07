# AliasSourceNotRegisteredError

**Symptom**

Raised naming the `source_type` an `Alias` points at, saying no provider is registered for it.

**Cause**

`Alias(source_type=X)` was declared, but no provider's `bound_type` resolves to `X` — either the
provider for `X` was never defined, its group wasn't passed to `Container(groups=[...])`, or it was
declared with `bound_type=None` (making it unresolvable by type, which an alias also can't reach).
This is checked eagerly during `validate()`, and again at resolve time if validation was skipped.

**Fix**

Register (and include) a provider for the source type before defining the alias:

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    # The alias's source must resolve by type — no bound_type=None here.
    impl = providers.Factory(scope=Scope.APP, creator=Implementation)

    interface_alias = providers.Alias(source_type=Implementation)
```

If the source provider lives in a different `Group`, make sure that group is also passed to
`Container(groups=[...])`. Run with `validate=True` so this is caught at startup rather than on first
resolve.

## See also

- [Alias](../providers/alias.md) — binding one type to an already-registered provider.
- [No provider registered for type](missing-provider.md) — the same "unregistered type" problem, without an alias in the way.
