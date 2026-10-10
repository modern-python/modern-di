# UnknownFactoryKwargError

## Symptom

```
modern_di.exceptions.registration.UnknownFactoryKwargError: Factory kwargs contain unknown key(s) not in create_service signature:
  - 'conection_string' (did you mean 'connection_string'?)
Known parameters: ['connection_string']
See: https://modern-di.modern-python.org/troubleshooting/unknown-factory-kwarg-error/
```

It is raised by the `Factory(...)` call, before any container exists. Each unknown key gets its own
line, in sorted order, with a `did you mean` hint when a parameter name is close to it. The exception
carries `.creator`, `.unknown_keys`, `.known_keys` and `.suggestions`.

## Cause

A key in `kwargs={...}` matches no parameter of the creator, usually a typo or a key left behind after
a parameter was renamed.

The check runs only when `modern-di` reads the creator's signature. It is skipped when the creator
takes `**kwargs`, when its signature cannot be read, and when the factory sets
`skip_creator_parsing=True`. In the last case a bad key surfaces at resolve time as
[`CreatorCallError`](creator-call-error.md).

## Fix

Match the `kwargs` keys to the creator's parameter names.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Service: ...


def create_service(connection_string: str) -> Service:
    return Service()
-->

<!-- raises: UnknownFactoryKwargError -->

```python
# Broken:
providers.Factory(create_service, scope=Scope.APP, kwargs={"conection_string": "..."})
```

```python
# Works:
class Dependencies(Group):
    service = providers.Factory(
        create_service, scope=Scope.APP, kwargs={"connection_string": "..."}
    )


assert isinstance(Container(groups=[Dependencies]).resolve(Service), Service)
```

## See also

- [Factories: kwargs](../providers/factories.md#kwargs): how static `kwargs` are passed to the creator.
- [CreatorCallError](creator-call-error.md): the resolve-time form of a `kwargs` mismatch.
