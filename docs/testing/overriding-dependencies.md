# Overriding Dependencies

Overriding dependencies is a powerful feature that allows you to replace provider implementations with mock objects or alternative implementations, primarily for testing purposes.

## Purpose

Dependency overriding enables you to:
- Replace real implementations with mocks during testing
- Substitute dependencies with test-specific implementations
- Isolate units of code for focused testing

## How It Works

The `override` method allows you to replace a provider's resolved value with a custom object. When the container resolves the overridden provider, it will return the overridden value instead of executing the provider's normal resolution logic.

## Usage

```python
from modern_di import AsyncContainer, Group, Scope, providers


class Dependencies(Group):
    database_service = providers.Singleton(Scope.APP, DatabaseService)
    user_service = providers.Factory(Scope.REQUEST, UserService, db=database_service.cast)


# Create container
container = AsyncContainer(groups=[Dependencies])
container.enter()

# Override the database service with a mock
mock_db = MockDatabaseService()
container.override(Dependencies.database_service, mock_db)

# When resolving user_service, it will receive the mock database service
user_service_instance = container.sync_resolve_provider(Dependencies.user_service)
# user_service_instance.db will be the mock_db instance
```

## In Testing

The most common use case for dependency overriding is in testing:

```python
import pytest
from modern_di import AsyncContainer

from app.ioc import Dependencies


@pytest.fixture
async def di_container() -> typing.AsyncIterator[AsyncContainer]:
    """APP-scope container fixture."""
    container = AsyncContainer(groups=ALL_GROUPS)
    container.enter()
    try:
        yield container
    finally:
        container.close()


@pytest.fixture
def mock_database_service(di_container: AsyncContainer) -> MockDatabaseService:
    """Override the database service with a mock."""
    mock_service = MockDatabaseService()
    di_container.override(Dependencies.database_service, mock_service)
    return mock_service


@pytest.mark.usefixtures("mock_database_service")
async def test_user_service_with_mocked_db(di_container: AsyncContainer) -> None:
    # The user service will receive the mocked database service
    user_service = await di_container.resolve_provider(Dependencies.user_service)
    
    # Test the user service with the mock
    result = await user_service.get_user(1)
    assert result is not None
```

## Important Notes

1. **Scope Awareness**: Overrides apply to the specific container instance where they're set. Child containers inherit overrides from their parent containers.

2. **Type Safety**: The override value must be compatible with the provider's expected type to maintain type safety.

3. **Temporary Nature**: Overrides are temporary and only affect the specific container instance. They don't modify the original provider definitions.

4. **Resetting Overrides**: To remove an override, you would need to create a new container instance or implement a reset mechanism (the framework doesn't provide a built-in reset method).

## Best Practices

1. **Use in Fixtures**: Set up overrides in pytest fixtures to ensure clean test isolation.

2. **Document Overrides**: Clearly document why and how dependencies are being overridden in your tests.

3. **Clean Up**: Ensure proper cleanup by using context managers or fixture teardown to close containers.
