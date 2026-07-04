# What is Dependency Injection?

Dependency Injection (DI) is a design pattern where dependencies are provided (injected) from outside rather than created inside a class.

## The Problem

Without DI, classes create their own dependencies, leading to tight coupling:

```python
class UserService:
    def __init__(self) -> None:
        self.email = EmailService()  # ❌ Tight coupling

    def register_user(self, email: str) -> None:
        self.email.send_email(email, "Welcome!")
```

**Issues:** Hard to test, can't swap implementations, hidden dependencies.

## The Solution

With DI, dependencies are injected from outside:

```python
class UserService:
    def __init__(self, email: EmailSender) -> None:  # ✅ Injected
        self.email = email

    def register_user(self, email: str) -> None:
        self.email.send_email(email, "Welcome!")
```

**Benefits:** Easy testing, loose coupling, explicit dependencies.

## Why Use Dependency Injection?

### 1. Testability

Inject mocks for testing:

```python
def test_user_service() -> None:
    mock_email = Mock(spec=EmailSender)
    service = UserService(email=mock_email)

    service.register_user("test@example.com")

    mock_email.send_email.assert_called_once()
```

### 2. Loose Coupling

Depend on abstractions, not implementations:

```python
class UserService:
    def __init__(self, cache: CacheBackend) -> None:
        self.cache = cache

# Swap implementations easily
service = UserService(cache=RedisCache())    # Production
service = UserService(cache=DictCache())     # Development
service = UserService(cache=MockCache())     # Testing
```

## Lifetime Management in DI

Objects can have different lifetime cycles (singleton, scoped, transient). `modern-di` expresses this with [Scopes](../providers/scopes.md) — APP for process-wide singletons, REQUEST for per-request resources, and so on. In modern-di's own terms: a provider's scope (APP/SESSION/REQUEST/…) decides how long an instance lives, and the presence of `cache` means one shared instance is reused while its absence means a fresh instance is created on each resolve. Here are examples:

```python

import uuid

from modern_di import Group, Scope, providers

class AppGroup(Group):
    # Cached for the whole app: one shared instance.
    # cache=True makes the provider a cached singleton (see the Factories page).
    config = providers.Factory(
        scope=Scope.APP,
        creator=AppConfig,
        cache=True
    )

    # Cached per request: one shared instance per request
    db_session = providers.Factory(
        scope=Scope.REQUEST,
        creator=DatabaseSession,
        cache=True
    )

    # No cache: a fresh instance each resolve
    request_id = providers.Factory(
        scope=Scope.REQUEST,
        creator=lambda: str(uuid.uuid4())
    )
```

## Manual DI vs modern-di

### Manual Wiring

```python
config = AppConfig()
db = DatabaseConnection(config)
email = EmailService(config)
user_service = UserService(db, email)
```

**Problems:** Unwieldy at scale, no lifetime management, scattered configuration.

### Using modern-di

```python
import dataclasses
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class AppConfig:
    db_host: str = "localhost"
    db_port: int = 5432


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DatabaseConnection:
    config: AppConfig  # ✅ Auto-injected from type hint


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UserService:
    db: DatabaseConnection  # ✅ Auto-injected


# Declare dependencies
class AppGroup(Group):
    config = providers.Factory(
        scope=Scope.APP,
        creator=AppConfig,
        cache=True
    )
    db = providers.Factory(scope=Scope.REQUEST, creator=DatabaseConnection)
    user_service = providers.Factory(scope=Scope.REQUEST, creator=UserService)


# Build the app-level container, then a request-scoped child for per-request providers
app_container = Container(scope=Scope.APP, groups=[AppGroup])
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    user_service = request_container.resolve(UserService)
```

## Why Choose modern-di?

### 1. Zero Boilerplate

Type annotations auto-wire dependencies - no manual registration needed.

### 2. Scope Management

Hierarchical containers with automatic inheritance:

```python
app_container = Container(groups=[AppGroup], scope=Scope.APP)
request_container = app_container.build_child_container(scope=Scope.REQUEST)

# Resolves from correct scope automatically
db_pool = request_container.resolve(DatabasePool)      # APP scope
db_session = request_container.resolve(DatabaseSession)  # REQUEST scope
```

### 3. Easy Testing

Override any dependency:

```python
@pytest.fixture
def test_container() -> Container:
    container = Container(groups=[AppGroup])
    container.override(AppGroup.db, Mock(spec=DatabaseConnection))
    return container
```

### 4. Resource Cleanup

Define finalizers for automatic cleanup:

```python
class AppGroup(Group):
    db_session = providers.Factory(
        scope=Scope.REQUEST,
        creator=DatabaseSession,
        cache=providers.CacheSettings(
            finalizer=lambda session: session.close()  # ✅ Define cleanup
        )
    )

# Automatic finalizer execution
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    session = request_container.resolve(DatabaseSession)
    # Finalizers called automatically on exit
```

### 5. Framework Integrations

Works with [every official framework integration](comparison.md#the-landscape).
For example, with FastAPI:

```python
from modern_di_fastapi import FromDI


@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    user_service: UserService = FromDI(UserService),
) -> dict:
    return {"user": user_service.get_user(user_id)}
```

## Summary

Dependency Injection:

- **Decouples** classes from dependencies
- **Improves testability** with easy mocking
- **Centralizes configuration**
- **Manages lifetimes** automatically

`modern-di` automates DI with minimal boilerplate through type annotations, providing scope management, testing utilities, and framework integrations.
