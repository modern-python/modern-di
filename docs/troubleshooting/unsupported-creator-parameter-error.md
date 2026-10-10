# UnsupportedCreatorParameterError

## Symptom

For a parameterized generic annotation:

```
modern_di.exceptions.registration.UnsupportedCreatorParameterError: Parameter 'items' of create_thing cannot be injected: parameterized generic annotation list[myapp.things.Item] cannot be resolved by type; pass the value via the kwargs parameter or give the parameter a default
See: https://modern-di.modern-python.org/troubleshooting/unsupported-creator-parameter-error/
```

For a positional-only parameter:

```
modern_di.exceptions.registration.UnsupportedCreatorParameterError: Parameter 'item' of create_thing cannot be injected: positional-only parameters cannot be passed by keyword; give the parameter a default
See: https://modern-di.modern-python.org/troubleshooting/unsupported-creator-parameter-error/
```

Both are raised by the `Factory(...)` call, before any container exists.

## Cause

The creator has a parameter `modern-di` cannot fill by type:

- A parameterized generic annotation (`list[Item]`, `dict[str, Item]`) with no default and no
  matching `kwargs` entry.
- A positional-only parameter with no default (`def create_thing(item: Item, /)`). `modern-di` passes
  every argument by keyword, so it cannot fill this one even when a provider for `Item` is registered.

## Fix

For a parameterized generic, the preferred fix is a default:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Item: ...


class Thing:
    def __init__(self, items: object = ()) -> None:
        self.items = items
-->

<!-- raises: UnsupportedCreatorParameterError -->

```python
# Broken:
def create_thing(items: list[Item]) -> Thing:
    return Thing(items)


providers.Factory(create_thing, scope=Scope.APP)
```

```python
def create_thing(items: tuple[Item, ...] = ()) -> Thing:
    return Thing(items)


class Dependencies(Group):
    thing = providers.Factory(create_thing, scope=Scope.APP)


assert Container(groups=[Dependencies]).resolve(Thing).items == ()
```

Or supply the value through `kwargs`:

```python
def create_thing(items: list[Item]) -> Thing:
    return Thing(items)


class Dependencies(Group):
    thing = providers.Factory(create_thing, scope=Scope.APP, kwargs={"items": []})


assert Container(groups=[Dependencies]).resolve(Thing).items == []
```

Or turn off signature parsing and supply every argument through `kwargs`. This suits a creator
with several parameters `modern-di` cannot wire. Pass `bound_type`, since the return annotation is
not read either:

```python
class Dependencies(Group):
    thing = providers.Factory(
        create_thing,
        scope=Scope.APP,
        skip_creator_parsing=True,
        bound_type=Thing,
        kwargs={"items": []},
    )


assert Container(groups=[Dependencies]).resolve(Thing).items == []
```

A positional-only parameter (`def create_thing(items: list[Item], /)`) can only be fixed with a
default. The other two fixes pass the value by keyword: a `kwargs` entry still raises this error, and
`skip_creator_parsing=True` raises [`CreatorCallError`](creator-call-error.md) at resolve. If you cannot give it a default, drop
the `/` or wrap the creator in a function that takes the parameter by keyword.

## See also

- [Factories: creator-signature support matrix](../providers/factories.md#creator-signature-support-matrix): which parameter shapes are wired.
- [CreatorCallError](creator-call-error.md): a `kwargs` mismatch found when the creator is called.
