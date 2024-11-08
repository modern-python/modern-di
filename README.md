"Modern-DI"
==

| Project            | Badges                                                                                                                                                                                                                                                                                          |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| common             | [![MyPy Strict](https://img.shields.io/badge/mypy-strict-blue)](https://mypy.readthedocs.io/en/stable/getting_started.html#strict-mode-and-configuration) [![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di)](https://github.com/modern-python/modern-di/stargazers) |
| modern-di          | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di.svg)](https://pypi.python.org/pypi/modern-di ) [![downloads](https://img.shields.io/pypi/dm/modern-di.svg)](https://pypistats.org/packages/modern-di)                                                                   |
| modern-di-fastapi  | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-fastapi.svg)](https://pypi.python.org/pypi/modern-di-fastapi) [![downloads](https://img.shields.io/pypi/dm/modern-di-fastapi.svg)](https://pypistats.org/packages/modern-di-fastapi)                                    |
| modern-di-litestar | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-litestar.svg)](https://pypi.python.org/pypi/modern-di-litestar) [![downloads](https://img.shields.io/pypi/dm/modern-di-litestar.svg)](https://pypistats.org/packages/modern-di-litestar)                                |

Dependency injection framework for Python inspired by `dependency-injector` and `dishka`.

It is in early development state and gives you the following:
- DI framework with IOC-container and scopes.
- Async and sync resolving.
- Python 3.10-3.13 support.
- Full coverage by types annotations (mypy in strict mode).
- Overriding dependencies for tests.
- Package with zero dependencies.

📚 [Documentation](https://modern-di.readthedocs.io)

## Describe resources and classes:
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
class DependentFactory:
    sync_resource: str
    async_resource: str
```

## Describe dependencies graph (IoC-container)
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

## Create container and resolve dependencies in your code
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
