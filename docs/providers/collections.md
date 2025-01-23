# Collections

There are several collection providers: `List` and `Dict`

## List

- List provider contains other providers.
- Resolves into list of dependencies.

```python
import random
from modern_di import BaseGraph, Container, Scope, providers


class Dependencies(BaseGraph):
    random_number = providers.Factory(Scope.APP, random.random)
    numbers_sequence = providers.List(Scope.APP, random_number, random_number)


with Container(scope=Scope.APP) as container:
    print(Dependencies.numbers_sequence.sync_resolve(container))
    # [0.3035656170071561, 0.8280498192037787]
```

## Dict

- Dict provider is a collection of named providers.
- Resolves into dict of dependencies.

```python
import random
from modern_di import BaseGraph, Container, Scope, providers


class Dependencies(BaseGraph):
    random_number = providers.Factory(Scope.APP, random.random)
    numbers_map = providers.Dict(Scope.APP, key1=random_number, key2=random_number)


with Container(scope=Scope.APP) as container:
    print(Dependencies.numbers_map.sync_resolve(container))
    # {'key1': 0.6851384528299208, 'key2': 0.41044920948045294}
```
