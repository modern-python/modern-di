# Modern DI

Welcome to the `modern-di` documentation!

`modern-di` is a python dependency injection framework which, among other things,
supports the following:

- Async and sync dependency resolution
- Scopes and granular context management
- Python 3.10+ support
- Fully typed and tested
- Integrations with `FastAPI`, `FastStream` and `LiteStar`

---

# Quickstart

## 1. Install `modern-di` using your favorite tool:

If you need only `modern-di` without integrations:


=== "uv"

    ```bash
    uv add modern-di
    ```

=== "pip"

    ```bash
    pip install modern-di
    ```

=== "poetry"

    ```bash
    poetry add modern-di
    ```

If you need to integrate with `fastapi` or `litestar`, then install `modern-di-fastapi` or `modern-di-litestar` accordingly.

## 2. Describe resources and classes:
```python
import dataclasses
import logging
import typing


logger = logging.getLogger(__name__)


# singleton provider with finalization
def create_sync_resource() -> typing.Iterator[str]:
    logger.debug("Resource initiated")
    try:
        yield "sync resource"
    finally:
        logger.debug("Resource destructed")


# same, but async
async def create_async_resource() -> typing.AsyncIterator[str]:
    logger.debug("Async resource initiated")
    try:
        yield "async resource"
    finally:
        logger.debug("Async resource destructed")


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleFactory:
    dep1: str
    dep2: int


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentFactory:
    sync_resource: str
    async_resource: str
```

## 3. Describe dependencies groups

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    sync_resource = providers.Resource(Scope.APP, create_sync_resource)
    async_resource = providers.Resource(Scope.APP, create_async_resource)

    simple_factory = providers.Factory(Scope.REQUEST, SimpleFactory, dep1="text", dep2=123)
    dependent_factory = providers.Factory(
        Scope.REQUEST,
        DependentFactory,
        sync_resource=sync_resource.cast,
        async_resource=async_resource.cast,
    )
```

## 4.1. Integrate with your framework

For now there are integration for the following frameworks:

1. [FastAPI](integrations/fastapi)
2. [FastStream](integrations/faststream)
3. [LiteStar](integrations/litestar)

## 4.2. Or use `modern-di` without integrations

Create container and resolve dependencies in your code
```python
from modern_di import AsyncContainer, SyncContainer, Scope


# For applications that need both sync and async resolution, use AsyncContainer
ALL_GROUPS = [Dependencies]

# init container of app scope in sync mode
container = SyncContainer(groups=ALL_GROUPS)
container.enter()

# resolve sync resource
Dependencies.sync_resource.sync_resolve(container)

# close container when done
container.close()

# init container of app scope in async mode
container = AsyncContainer(groups=ALL_GROUPS)
container.enter()

# resolve async resource
await Dependencies.async_resource.resolve(container)

# resolve sync resource
instance1 = container.sync_resolve_provider(Dependencies.sync_resource)
instance2 = container.sync_resolve_provider(Dependencies.sync_resource)
assert instance1 is instance2

# You can also resolve by type if you've registered groups
instance3 = container.sync_resolve(str)  # resolves the sync_resource

# create container of request scope
async with container.build_child_container(scope=Scope.REQUEST) as request_container:
    # resolve factories of request scope
    container.sync_resolve_provider(Dependencies.simple_factory)
    await container.resolve_provider(Dependencies.dependent_factory)

    # resources of app-scope also can be resolved here

# close container when done
container.close()
```