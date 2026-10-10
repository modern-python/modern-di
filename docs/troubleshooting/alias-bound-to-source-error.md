# AliasBoundToSourceError

## Symptom

```
modern_di.exceptions.registration.AliasBoundToSourceError: Alias of <class 'myapp.ioc.Implementation'> is bound to its own source type, so it would resolve to itself. Pass bound_type= with the type the alias should answer for, such as a base class or Protocol, or bound_type=None to resolve it by reference only.
See: https://modern-di.modern-python.org/troubleshooting/alias-bound-to-source-error/
```

It is raised by the `Alias(...)` call itself, before any container exists. `.source_type` holds the
type the alias points at. The class descends from `RegistrationError`; see
[Errors and exceptions](../providers/errors-and-exceptions.md).

## Cause

An alias is registered under its `bound_type`. With `bound_type` equal to `source_type`, the alias
registers itself as the provider for its own source. If nothing else provides that type, the alias
resolves to itself, a one-node cycle. If something does, the two collide as duplicates. Neither does
anything useful, so the declaration is rejected.

<!-- invisible-code-block: python
from typing import Protocol

from modern_di import Container, Group, providers


class Interface(Protocol): ...


class Implementation: ...
-->

<!-- raises: AliasBoundToSourceError -->

```python
# Broken:
providers.Alias(Implementation, bound_type=Implementation)
```

## Fix

Pass the type the alias should answer for, such as a base class or a `Protocol`:

```python
# Works:
class Dependencies(Group):
    impl = providers.Factory(Implementation)
    interface_alias = providers.Alias(Implementation, bound_type=Interface)


assert isinstance(Container(groups=[Dependencies]).resolve(Interface), Implementation)
```

To use the alias only by reference, through `container.resolve_provider(...)` or as a `kwargs=`
value, pass `bound_type=None`.

## See also

- [Alias](../providers/alias.md): binding one type to an already registered provider.
- [AliasSourceNotRegisteredError](alias-source-not-registered-error.md): an alias whose source has no provider.
