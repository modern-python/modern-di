# Resource
- Resources are initialized only once per scope and have teardown logic.
- Generator or async generator is required.
```python
import typing

from modern_di import BaseGraph, Container, Scope, providers


def create_sync_resource() -> typing.Iterator[str]:
    # resource initialization
    try:
        yield "sync resource"
    finally:
        pass  # resource teardown


async def create_async_resource() -> typing.AsyncIterator[str]:
    # resource initialization
    try:
        yield "async resource"
    finally:
        pass  # resource teardown


class Dependencies(BaseGraph):
    sync_resource = providers.Resource(Scope.APP, create_sync_resource)
    async_resource = providers.Resource(Scope.REQUEST, create_async_resource)


with Container(scope=Scope.APP) as container:
    # sync resource of app scope
    sync_resource_instance = Dependencies.sync_resource.sync_resolve(container)
    async with container.build_child_container(scope=Scope.REQUEST) as request_container:
        # async resource of request scope
        async_resource_instance = await Dependencies.async_resource.async_resolve(request_container)
```
