# GroupInstantiationError

## Symptom

```
modern_di.exceptions.lifecycle.GroupInstantiationError: Dependencies cannot be instantiated
See: https://modern-di.modern-python.org/troubleshooting/group-instantiation-error/
```

`.group_name` holds the name of the `Group` subclass.

## Cause

A `Group` subclass was called like a constructor, `Dependencies()`. A group is a namespace for
declaring providers as class attributes, and calling it always raises, with or without arguments.
You pass the class itself to `Container(groups=[Dependencies])` and read its providers as
`Dependencies.some_provider`.

The habit often comes from `dependency-injector` and `that-depends`, where the container class is
also the runtime object you resolve from. The migration guides cover the difference:
[from `dependency-injector`](../migration/from-dependency-injector.md#2-key-conceptual-shifts) and
[from `that-depends`](../migration/from-that-depends.md#2-key-conceptual-shifts).

## Fix

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Service: ...


class Dependencies(Group):
    service = providers.Factory(Service, scope=Scope.APP)
-->

<!-- raises: GroupInstantiationError -->

```python
# Broken:
deps = Dependencies()
```

Pass the class to a `Container` and resolve from the container:

```python
# Works:
container = Container(groups=[Dependencies])
service = container.resolve_provider(Dependencies.service)
assert isinstance(service, Service)
```

## See also

- [Organize a large container with multiple Groups](../recipes/multi-group.md): splitting providers across several `Group` classes.
- [Migration from `dependency-injector`](../migration/from-dependency-injector.md): `Group` as schema, `Container` as runtime.
- [Migration from `that-depends`](../migration/from-that-depends.md): the same split, coming from `BaseContainer`.
