# AliasSourceNotRegisteredError

## Symptom

```
modern_di.exceptions.resolution.AliasSourceNotRegisteredError: Cannot resolve dependency chain:
  APP  Interface
  caused by: Alias source type <class 'myapp.alias.Implementation'> is not registered in providers registry. Register a provider for <class 'myapp.alias.Implementation'> before the alias is resolved.
See: https://modern-di.modern-python.org/troubleshooting/alias-source-not-registered-error/
```

`resolve()` and `resolve_provider()` raise it with the chain shown above. `container.validate()`
reports it inside [`ValidationFailedError`](validation-failed-error.md), without the chain. `.source_type`
holds the type the alias points at.

## Cause

`Alias(X, bound_type=...)` delegates to whatever provider is registered under `X`, and none is. One of
these applies:

- No provider for `X` was ever declared.
- The group that declares it was not passed to `Container(groups=[...])`.
- The provider for `X` was declared with `bound_type=None`. The alias looks its source up by type, so a
  provider that is reachable only by reference does not count, and the message still says
  `not registered`.

## Fix

Register a provider for the source type under that type, and pass its group to the container:

```python
from typing import Protocol

from modern_di import Container, Group, Scope, providers


class Interface(Protocol): ...


class Implementation: ...


class Dependencies(Group):
    impl = providers.Factory(Implementation, scope=Scope.APP)
    interface_alias = providers.Alias(Implementation, bound_type=Interface)


container = Container(groups=[Dependencies])
container.validate()
assert isinstance(container.resolve(Interface), Implementation)
```

The source only has to be registered by the time the alias is first resolved, so a provider added
later with `container.add_providers(...)` also works. Calling `container.validate()` at startup
reports a missing source before the first request.

## See also

- [Alias](../providers/alias.md): binding one type to an already registered provider.
- [ProviderNotRegisteredError](missing-provider.md): the same gap without an alias in the way.
- [ValidationFailedError](validation-failed-error.md): how `validate()` groups the errors it finds.
