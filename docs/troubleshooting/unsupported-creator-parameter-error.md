# UnsupportedCreatorParameterError

## Symptom

Raised at `Factory(...)` declaration time, naming the creator, the parameter, and the reason it can't
be wired automatically.

## Cause

The creator has a parameter shape `modern-di` cannot resolve by type: a positional-only parameter with
no default (`def f(x, /)`), or a parameterized generic annotation (`list[X]`, `dict[str, Y]`, etc.)
with no default and no matching `kwargs` entry. Both are declaration-time checks, not resolve-time
ones.

## Fix

For a parameterized generic, pick one of three escape routes, in order of preference:

<!-- invisible-code-block: python
from modern_di import Group, Scope, providers


class Item: ...


class Thing: ...
-->

```python
def create_thing(items: list[Item]) -> Thing: ...


class Dependencies(Group):
    # 1. Give the parameter a default
    #    def create_thing(items: list[Item] = ()) -> Thing: ...

    # 2. Supply the value via kwargs at declaration time
    thing = providers.Factory(create_thing, scope=Scope.APP, kwargs={"items": []})

    # 3. Skip creator parsing entirely and supply every argument via kwargs
    thing2 = providers.Factory(
        create_thing,
        scope=Scope.APP,
        skip_creator_parsing=True,
        bound_type=Thing,
        kwargs={"items": []},
    )
```

A positional-only parameter (`def create_thing(items: list[Item], /)`) can only be fixed with route
1. Routes 2 and 3 pass the value by keyword, so route 2 still raises this error and route 3 raises
`CreatorCallError` at resolve. If you can't give it a default, drop the `/` or wrap the creator in a
function that takes the parameter by keyword.

## Escape hatches

`skip_creator_parsing=True` bypasses signature parsing altogether (option 3 above). Use it when a
creator has several unsupported keyword-passable parameters rather than fixing each one individually.

## See also

- [Factories: creator-signature support matrix](../providers/factories.md#creator-signature-support-matrix).
