# Collections

There are several collection providers: `List` and `Dict`

## List

- The List provider contains other providers.
- It resolves into a list of dependencies.

```python
import random
from modern_di import Group, Container, Scope, providers


class Dependencies(Group):
    random_number = providers.Factory(Scope.APP, random.random)
    numbers_sequence = providers.List(Scope.APP, random_number, random_number)


container = Container(groups=[Dependencies])
print(container.sync_resolve_provider(Dependencies.numbers_sequence))
# [0.3035656170071561, 0.8280498192037787]
```

## Dict

- The Dict provider is a collection of named providers.
- It resolves into a dict of dependencies.

```python
import random
from modern_di import Group, Container, Scope, providers


class Dependencies(Group):
    random_number = providers.Factory(Scope.APP, random.random)
    numbers_map = providers.Dict(Scope.APP, key1=random_number, key2=random_number)


container = Container(groups=[Dependencies])
print(container.sync_resolve_provider(Dependencies.numbers_map))
# {'key1': 0.6851384528299208, 'key2': 0.41044920948045294}
```
