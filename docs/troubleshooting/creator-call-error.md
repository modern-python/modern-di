# CreatorCallError

## Symptom

```
modern_di.exceptions.resolution.CreatorCallError: Cannot resolve dependency chain:
  APP  Service (myapp.creator:7)
  caused by: Failed to call creator create_service: create_service() missing 1 required positional argument: 'port'. Check kwargs and skip_creator_parsing usage.
See: https://modern-di.modern-python.org/troubleshooting/creator-call-error/
```

It is raised at resolve time. `.creator` holds the creator, and `.original_error` holds the binding
`TypeError`, which is also the exception's `__cause__`.

## Cause

The arguments `modern-di` assembled, static `kwargs` plus resolved dependencies, do not fit the
creator's signature. This usually comes from `skip_creator_parsing=True`, where nothing is wired
by type and `kwargs` must supply every required argument. The `TypeError` then says which part is
wrong:

- `missing 1 required positional argument`: `kwargs` leaves out a required parameter.
- `got an unexpected keyword argument`: `kwargs` has a key the creator does not take.
- `got some positional-only arguments passed as keyword arguments`: `kwargs` names a positional-only
  parameter.

`container.validate()` cannot catch any of these, because with `skip_creator_parsing=True` there is
no parsed signature to check `kwargs` against. Without `skip_creator_parsing`, an unknown key is
rejected when the `Factory` is declared, as
[`UnknownFactoryKwargError`](unknown-factory-kwarg-error.md).

An exception raised inside the creator's body, a `TypeError` included, propagates as itself and is
never wrapped in this error.
A `ResolutionError` raised by a `container.resolve()` call in the body keeps its class too, and gains
the creator's step in its `.dependency_path`, so its message draws the chain down to that creator.

## Fix

Make `kwargs` cover exactly what the signature requires.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Service: ...


def create_service(host: str, port: int) -> Service:
    return Service()
-->

<!-- raises: CreatorCallError -->

```python
# Broken:
class Dependencies(Group):
    service = providers.Factory(
        create_service,
        scope=Scope.APP,
        skip_creator_parsing=True,
        bound_type=Service,
        kwargs={"host": "localhost"},
    )


Container(groups=[Dependencies]).resolve(Service)
```

```python
# Works:
class Dependencies(Group):
    service = providers.Factory(
        create_service,
        scope=Scope.APP,
        skip_creator_parsing=True,
        bound_type=Service,
        kwargs={"host": "localhost", "port": 5432},
    )


assert isinstance(Container(groups=[Dependencies]).resolve(Service), Service)
```

## See also

- [UnknownFactoryKwargError](unknown-factory-kwarg-error.md): the declaration-time form of a `kwargs` mismatch.
- [Factories: skip_creator_parsing](../providers/factories.md#skip_creator_parsing): what turning off wiring changes.
- [UnsupportedCreatorParameterError](unsupported-creator-parameter-error.md): parameter shapes that cannot be wired by type.
