# Fixtures for testing

## 1. Add required fixtures:

```python
import typing

import fastapi
import modern_di
import modern_di_fastapi
import pytest

from app import ioc


# The application object can be imported from somewhere
application = fastapi.FastAPI()
modern_di_fastapi.setup_di(application, modern_di.Container(groups=ioc.ALL_GROUPS))


@pytest.fixture
async def di_container() -> typing.AsyncIterator[modern_di.Container]:
    """Fixture with APP-scope container."""
    di_container_: typing.Final = modern_di_fastapi.fetch_di_container(application)
    try:
        yield di_container_
    finally:
        await di_container_.close_async()


@pytest.fixture
async def request_di_container(di_container: modern_di.Container) -> typing.AsyncIterator[modern_di.Container]:
    di_container_ = di_container.build_child_container(scope=modern_di.Scope.REQUEST)
    try:
        yield di_container_
    finally:
        await di_container_.close_async()


@pytest.fixture
def mock_dependencies(di_container: modern_di.Container) -> None:
    # Override dependencies using the new API
    di_container.override(
        provider=Dependencies.simple_factory,
        override_object=SimpleFactory(dep1="mock", dep2=777)
    )
```

## 2. Use fixtures in tests:

```python
import pytest
from modern_di import Container

from app.ioc import Dependencies


def test_with_app_scope(di_container: Container) -> None:
    resource_instance = di_container.resolve_provider(Dependencies.sync_resource)
    # Do something with the dependency


def test_with_request_scope(request_di_container: Container) -> None:
    simple_factory_instance = request_di_container.resolve_provider(Dependencies.simple_factory)
    # Do something with the dependency

@pytest.mark.usefixtures("mock_dependencies")
def test_with_request_scope_mocked(request_di_container: Container) -> None:
    simple_factory_instance = request_di_container.resolve_provider(Dependencies.simple_factory)
    # The dependency is mocked here
```
