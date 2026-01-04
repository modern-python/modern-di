# Factories
Factories are initialized on every call.

## Factory
- A class or simple function is allowed.

```python
import dataclasses

from modern_di import Group, Container, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class IndependentFactory:
    dep1: str
    dep2: int


class Dependencies(Group):
    independent_factory = providers.Factory(Scope.APP, IndependentFactory, dep1="text", dep2=123)


container = Container(groups=[Dependencies])
instance = container.sync_resolve_provider(Dependencies.independent_factory)
assert isinstance(instance, IndependentFactory)
```
