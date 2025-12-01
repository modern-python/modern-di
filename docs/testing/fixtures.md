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
modern_di_fastapi.setup_di(application, groups=ioc.ALL_GROUPS)


@pytest.fixture
async def di_container() -> typing.AsyncIterator[modern_di.AsyncContainer]:
    """Fixture with APP-scope container."""
    di_container_: typing.Final = modern_di_fastapi.fetch_di_container(application)
    di_container_.enter()
    try:
        yield di_container_
    finally:
        di_container_.close()


@pytest.fixture
async def request_di_container(di_container: modern_di.AsyncContainer) -> typing.AsyncIterator[modern_di.AsyncContainer]:
    """Fixture with REQUEST-scope container."""
    async with di_container.build_child_container(scope=modern_di.Scope.REQUEST) as request_container:
        yield request_container


@pytest.fixture
def mock_dependencies(di_container: modern_di.AsyncContainer) -> None:
    """Mock dependencies for tests."""
    # Override dependencies using the new API
    di_container.override(ioc.Dependencies.simple_factory, ioc.SimpleFactory(dep1="mock", dep2=777))
```

## 2. Use fixtures in tests:

```python
import pytest
from modern_di import AsyncContainer

from app.ioc import Dependencies


async def test_with_app_scope(di_container: AsyncContainer) -> None:
    sync_resource_instance = await di_container.resolve_provider(Dependencies.sync_resource)
    # do sth with dependency


async def test_with_request_scope(request_di_container: AsyncContainer) -> None:
    simple_factory_instance = await request_di_container.resolve_provider(Dependencies.simple_factory)
    # do sth with dependency

@pytest.mark.usefixtures("mock_dependencies")
async def test_with_request_scope_mocked(request_di_container: AsyncContainer) -> None:
    simple_factory_instance = await request_di_container.resolve_provider(Dependencies.simple_factory)
    # dependency is mocked here
```
