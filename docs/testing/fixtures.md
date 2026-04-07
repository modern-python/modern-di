# Fixtures for testing

## 1. Add required fixtures:

```python
import typing

import fastapi
import modern_di
import modern_di_fastapi
import pytest

from app import ioc
from app.ioc import Dependencies, SimpleFactory


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
    """Fixture with REQUEST-scope container."""
    di_container_ = di_container.build_child_container(scope=modern_di.Scope.REQUEST)
    try:
        yield di_container_
    finally:
        await di_container_.close_async()


@pytest.fixture
def mock_dependencies(di_container: modern_di.Container) -> typing.Iterator[None]:
    di_container.override(
        provider=Dependencies.simple_factory,
        override_object=SimpleFactory(dep1="mock", dep2=777)
    )
    yield
    di_container.reset_override(Dependencies.simple_factory)
```

!!! note "Overrides are global"
    `container.override()` and `container.reset_override()` operate on the shared overrides registry, which is shared across all containers in the same tree (parent and all children). Calling `override()` on a child container affects every container in the tree for the duration of the override. Always call `reset_override()` in a `finally` block or use a fixture that guarantees cleanup.

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
