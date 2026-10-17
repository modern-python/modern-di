# AliasSourceNotRegisteredError

## Symptom

```
modern_di.exceptions.resolution.AliasSourceNotRegisteredError: Cannot resolve dependency chain:
  APP  Interface
  caused by: Alias source type <class 'myapp.alias.Implementation'> is not registered in providers registry. Register a provider for <class 'myapp.alias.Implementation'> before the alias is resolved.
See: https://modern-di.modern-python.org/troubleshooting/alias-source-not-registered-error/
```

When the only provider for the source type is a reference-only provider, the message names that
provider instead:

```
modern_di.exceptions.resolution.AliasSourceNotRegisteredError: Cannot resolve dependency chain:
  APP  Interface
  caused by: Alias source type <class 'myapp.alias.Implementation'> is not registered by type: this provider serves it with bound_type=None, and an alias cannot reach a reference-only provider.
  - ReferenceOnly.impl: Factory (myapp.alias:14)
Give it bound_type=Implementation, or remove bound_type=None.
See: https://modern-di.modern-python.org/troubleshooting/alias-source-not-registered-error/
```

`resolve()` and `resolve_provider()` raise it with the chain shown above. `container.validate()`
reports it inside [`ValidationFailedError`](validation-failed-error.md), without the chain. `.source_type`
holds the type the alias points at, and `.reference_only_providers` lists the reference-only
providers whose creator returns it.

## Cause

`Alias(X, bound_type=...)` delegates to whatever provider is registered under `X`, and none is. One of
these applies:

- No provider for `X` was ever declared.
- The group that declares it was not passed to `Container(groups=[...])`.
- The provider for `X` was declared with `bound_type=None`, which makes it a reference-only provider.
  The alias looks its source up by type, so it cannot reach that provider. The message lists every
  reference-only `Factory` whose creator is annotated to return `X`. One declared with
  `skip_creator_parsing=True` has no parsed return type, so the message cannot name it.

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

### The source is a reference-only provider

A `bound_type=None` provider is never registered under its type, so an alias cannot use it as a
source:

```python
# Broken:
class ReferenceOnly(Group):
    impl = providers.Factory(Implementation, bound_type=None)
    interface_alias = providers.Alias(Implementation, bound_type=Interface)
```

<!-- raises: AliasSourceNotRegisteredError -->

```python
Container(groups=[ReferenceOnly]).resolve(Interface)
```

Drop `bound_type=None`, so the provider binds under its creator's return type, or pass that type
explicitly:

```python
# Works:
class BoundByType(Group):
    impl = providers.Factory(Implementation, bound_type=Implementation)
    interface_alias = providers.Alias(Implementation, bound_type=Interface)


assert isinstance(Container(groups=[BoundByType]).resolve(Interface), Implementation)
```

## See also

- [Alias](../providers/alias.md): binding one type to an already registered provider.
- [ProviderNotRegisteredError](missing-provider.md): the same gap without an alias in the way.
- [ValidationFailedError](validation-failed-error.md): how `validate()` groups the errors it finds.
