# UnsupportedCreatorParameterError

**Symptom**

Raised at `Factory(...)` declaration time, naming the creator, the parameter, and the reason it can't
be wired automatically.

**Cause**

The creator has a parameter shape `modern-di` cannot resolve by type: a positional-only parameter with
no default (`def f(x, /)`), or a parameterized generic annotation (`list[X]`, `dict[str, Y]`, etc.)
with no default and no matching `kwargs` entry. Both are declaration-time checks, not resolve-time
ones.

**Fix**

Pick one of three escape routes, in order of preference:

```python
def create_thing(items: list[Item], /) -> Thing: ...


class Dependencies(Group):
    # 1. Give the parameter a default
    #    def create_thing(items: list[Item] = ()) -> Thing: ...

    # 2. Supply the value via kwargs at declaration time
    thing = providers.Factory(scope=Scope.APP, creator=create_thing, kwargs={"items": []})

    # 3. Skip creator parsing entirely and supply every argument via kwargs
    thing2 = providers.Factory(
        scope=Scope.APP, creator=create_thing, skip_creator_parsing=True, kwargs={"items": []}
    )
```

**Escape hatches**

`skip_creator_parsing=True` bypasses signature parsing altogether (option 3 above) — use it when a
creator has several unsupported parameter shapes rather than fixing each one individually.

## See also

- [Factories: creator-signature support matrix](../providers/factories.md#creator-signature-support-matrix).
