# Resource

- Resources are initialized only once per scope and have teardown logic.
- A generator or async generator is required.

```python
import typing

from modern_di import Group, AsyncContainer, Scope, providers


def create_sync_resource() -> typing.Iterator[str]:
    # Resource initialization
    try:
        yield "sync resource"
    finally:
        pass  # Resource teardown


async def create_async_resource() -> typing.AsyncIterator[str]:
    # Resource initialization
    try:
        yield "async resource"
    finally:
        pass  # Resource teardown


class Dependencies(Group):
    sync_resource = providers.Resource(Scope.APP, create_sync_resource)
    async_resource = providers.Resource(Scope.REQUEST, create_async_resource)


# For synchronous resolution
with AsyncContainer() as container:
    # sync resource of app scope
    sync_resource_instance = container.sync_resolve_provider(Dependencies.sync_resource)
    with container.build_child_container(scope=Scope.REQUEST) as request_container:
        # async resource of request scope
        async_resource_instance = await request_container.resolve_provider(Dependencies.async_resource)
```

## Concurrency safety

`Resource` is safe to use in threading and asyncio concurrency:

```python
async with AsyncContainer() as container:
    # Calling resolve_provider concurrently in different coroutines will create only one instance
    await container.resolve_provider(Dependencies.sync_resource)

    # Calling sync_resolve_provider concurrently in different threads will create only one instance
    container.sync_resolve_provider(Dependencies.sync_resource)
```
