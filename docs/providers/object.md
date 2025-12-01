# Object

Object provider returns an object “as is”.

```python
from modern_di import Group, AsyncContainer, Scope, providers


class Dependencies(Group):
    object_provider = providers.Object(Scope.APP, 1)


with AsyncContainer(groups=[Dependencies], scope=Scope.APP) as container:
    assert container.sync_resolve_provider(Dependencies.object_provider) == 1
```
