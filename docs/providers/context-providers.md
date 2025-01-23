# Context Providers

There are several providers with access to container's context.

## Selector

- Receives context unpacked to callable object.
- Selector provider chooses between a provider based on a key.
- Resolves into a single dependency.

```python
import typing

from modern_di import BaseGraph, Container, Scope, providers


class StorageService(typing.Protocol):
    ...

class StorageServiceLocal(StorageService):
    ...

class StorageServiceRemote(StorageService):
    ...

def selector_function(*, storage_backend: str | None = None, **_: object) -> str:
    return storage_backend or "local"

class Dependencies(BaseGraph):
    storage_service: providers.Selector[StorageService] = providers.Selector(
        Scope.APP,
        selector_function,
        local=providers.Factory(Scope.APP, StorageServiceLocal),
        remote=providers.Factory(Scope.APP, StorageServiceRemote),
    )

with Container(scope=Scope.APP, context={"storage_backend": "remote"}) as container:
    print(type(Dependencies.storage_service.sync_resolve(container)))
    # StorageServiceRemote
```

## ContextAdapter

- Receives context unpacked to callable object.
- Can be used in another providers to access data from context.

```python
from modern_di import BaseGraph, Container, Scope, providers


def context_adapter_function(*, storage_backend: str | None = None, **_: object) -> str:
    return storage_backend or "local"

class Dependencies(BaseGraph):
    context_adapter = providers.ContextAdapter(Scope.APP, context_adapter_function)

with Container(scope=Scope.APP, context={"storage_backend": "remote"}) as container:
    print(Dependencies.context_adapter.sync_resolve(container))
    # "remote"
```
