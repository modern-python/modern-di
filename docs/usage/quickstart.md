# Quickstart

## 1. Install `modern-di` using your favorite tool:

If you need only `modern-di` without integrations:

```shell
pip install modern-di
uv add modern-di
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

## 3. Describe dependencies graph
```python
from modern_di import BaseGraph, Scope, providers


class Dependencies(BaseGraph):
    sync_resource = providers.Resource(Scope.APP, create_sync_resource)
    async_resource = providers.Resource(Scope.APP, create_async_resource)

    simple_factory = providers.Factory(Scope.REQUEST, SimpleFactory, dep1="text", dep2=123)
    dependent_factory = providers.Factory(
        Scope.REQUEST,
        sync_resource=sync_resource,
        async_resource=async_resource,
    )
```

## 4.1. Integrate with your framework

For now there are integration for the following frameworks:
```{eval-rst}
.. toctree::
    :maxdepth: 1

    ../integrations/fastapi
    ../integrations/litestar
```

## 4.2. Or use `modern-di` without integrations

Create container and resolve dependencies in your code
```python
from modern_di import Container, Scope


# init container of app scope in sync mode
with Container(scope=Scope.APP) as app_container:
    # resolve sync resource
    Dependencies.sync_resource.sync_resolve(app_container)


# init container of app scope in async mode
async with Container(scope=Scope.APP) as app_container:
    # resolve async resource
    await Dependencies.async_resource.async_resolve(app_container)

    # resolve sync resource
    instance1 = await Dependencies.sync_resource.async_resolve(app_container)
    instance2 = Dependencies.sync_resource.sync_resolve(app_container)
    assert instance1 is instance2

    # create container of request scope
    async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
        # resolve factories of request scope
        Dependencies.simple_factory.sync_resolve(request_container)
        await Dependencies.dependent_factory.async_resolve(request_container)
        
        # resources of app-scope also can be resolved here

```