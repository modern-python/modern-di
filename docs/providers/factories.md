# Factory

- initialized on every call;
- class or simple function is allowed.

## How it works

```python
import dataclasses

from modern_di import BaseGraph, Container, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class IndependentFactory:
    dep1: str
    dep2: int


class Dependencies(BaseGraph):
    independent_factory = providers.Factory(Scope.APP, IndependentFactory, dep1="text", dep2=123)


with Container(scope=Scope.APP) as container:
    instance = Dependencies.independent_factory.sync_resolve(container)
    assert isinstance(instance, IndependentFactory)
```
