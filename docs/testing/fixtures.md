# Fixtures for testing

## 1. Add required fixtures:

```python
import typing

import fastapi
import modern_di
import modern_di_fastapi
import pytest

from app import ioc


# application object can be imported from somewhere
application = fastapi.FastAPI()
modern_di_fastapi.setup_di(application)


@pytest.fixture
async def di_container() -> typing.AsyncIterator[modern_di.Container]:
    """Fixture with APP-scope container."""
    di_container_: typing.Final = modern_di_fastapi.fetch_di_container(application)
    async with di_container_:
        yield di_container_


@pytest.fixture
async def request_di_container(di_container: modern_di.Container) -> typing.AsyncIterator[modern_di.Container]:
    """Fixture with REQUEST-scope container."""
    async with di_container.build_child_container(scope=modern_di.Scope.REQUEST) as request_container:
        yield request_container


@pytest.fixture
def mock_dependencies(di_container: modern_di.Container) -> None:
    """Mock dependencies for tests."""
    ioc.Dependencies.simple_factory.override(ioc.SimpleFactory(dep1="mock", dep2=777), container=di_container)
```

## 2. Use fixtures in tests:

```python
import pytest
from modern_di import Container

from app.ioc import Dependencies


async def test_with_app_scope(di_container: Container) -> None:
    sync_resource_instance = await Dependencies.sync_resource.async_resolve(di_container)
    # do sth with dependency


async def test_with_request_scope(request_di_container: Container) -> None:
    simple_factory_instance = await Dependencies.simple_factory.async_resolve(request_di_container)
    # do sth with dependency

@pytest.mark.usefixtures("mock_dependencies")
async def test_with_request_scope_mocked(request_di_container: Container) -> None:
    simple_factory_instance = await Dependencies.simple_factory.async_resolve(request_di_container)
    # dependency is mocked here
```
