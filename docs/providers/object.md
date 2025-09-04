# Object

Object provider returns an object “as is”.

```python
from modern_di import Group, Container, Scope, providers


class Dependencies(Group):
    object_provider = providers.Object(Scope.APP, 1)


with Container(scope=Scope.APP) as container:
    assert Dependencies.object_provider.sync_resolve(container) == 1
```
