# modern-di — Testing

## Override a provider with a mock

```python
from unittest.mock import Mock
from modern_di import Container, Scope
from app.ioc import Dependencies
from app.repositories import UsersRepository
from app.services import UserService

def test_user_service_with_mock_repo():
    container = Container(scope=Scope.APP, groups=[Dependencies])
    mock_repo = Mock(spec=UsersRepository)
    
    container.override(Dependencies.users_repository, mock_repo)
    service = container.resolve(UserService)
    
    assert service.repo is mock_repo
    
    container.reset_override(Dependencies.users_repository)
```

**Important**: override before the first resolve, or a cached instance will be returned instead
of the mock.

`reset_override()` with no arguments clears all overrides.

## pytest fixture for clean override teardown

```python
import pytest
from unittest.mock import Mock
from modern_di import Container, Scope
from app.ioc import Dependencies

@pytest.fixture
def mock_repo():
    container = Container(scope=Scope.APP, groups=[Dependencies])
    mock = Mock(spec=UsersRepository)
    container.override(Dependencies.users_repository, mock)
    yield mock
    container.reset_override(Dependencies.users_repository)
```

Or use the container as a context manager — overrides are reset on exit:

```python
def test_with_context_manager():
    with Container(scope=Scope.APP, groups=[Dependencies]) as container:
        container.override(Dependencies.users_repository, Mock(spec=UsersRepository))
        service = container.resolve(UserService)
        # overrides reset automatically on __exit__
```

## Test scope chains

```python
async def test_request_scope_caching():
    app = Container(scope=Scope.APP, groups=[Dependencies])
    req = app.build_child_container(scope=Scope.REQUEST)

    # Same instance within one request container
    repo1 = req.resolve_provider(Dependencies.users_repository)
    repo2 = req.resolve_provider(Dependencies.users_repository)
    assert repo1 is repo2

    await req.close_async()   # triggers finalizers (e.g. session.close())
    await app.close_async()
```

```python
async def test_different_requests_get_different_instances():
    app = Container(scope=Scope.APP, groups=[Dependencies])
    req1 = app.build_child_container(scope=Scope.REQUEST)
    req2 = app.build_child_container(scope=Scope.REQUEST)

    repo1 = req1.resolve_provider(Dependencies.users_repository)
    repo2 = req2.resolve_provider(Dependencies.users_repository)
    assert repo1 is not repo2

    await req1.close_async()
    await req2.close_async()
    await app.close_async()
```

## Inject context in tests (ContextProvider)

```python
async def test_with_request_context():
    mock_request = Mock(spec=fastapi.Request)
    app = Container(scope=Scope.APP, groups=[Dependencies])
    req = app.build_child_container(
        scope=Scope.REQUEST,
        context={fastapi.Request: mock_request},
    )
    logger = req.resolve_provider(Dependencies.audit_logger)
    assert logger.request is mock_request
    await req.close_async()
```

## pytest config

modern-di tests use `asyncio_mode = "auto"` — async test functions work without extra markers:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Validate wiring without instantiating

Check that all dependencies can be resolved without creating real objects:

```python
def test_wiring():
    container = Container(scope=Scope.APP, groups=[Dependencies])
    container.validate_provider(Dependencies.users_repository)
    # Raises RuntimeError if any dependency is missing
```
