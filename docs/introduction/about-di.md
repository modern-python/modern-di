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

### 2. Loose coupling

Depend on abstractions, not concrete implementations, so the class using them never changes when
you swap `RedisCache` for `DictCache` in development or `MockCache` in tests.

## Manual wiring doesn't scale

As an app grows, someone has to build every object by hand, in the right order:

```python
config = AppConfig()
db = DatabaseConnection(config)
email = EmailService(config)
user_service = UserService(db, email)
```

This is unwieldy at scale, has no lifetime management, and scatters construction logic wherever a
dependency is needed. A DI container takes over that construction: `modern-di` reads your classes'
type hints and builds the graph for you — see the [Quickstart](../index.md#2-first-success).

## Lifetime management

Objects can have different lifetimes — singleton, per-request, or a fresh instance every call.
`modern-di` expresses this with [Scopes](../providers/scopes.md): a provider's scope decides how
long its instances live, and `cache=True` decides whether an instance is shared or rebuilt on each
resolve — see [Cached factories](../providers/factories.md#cached-factories).

## See also

- [modern-di vs other libraries](comparison.md) — including whether you need a container at all.
- [Quickstart](../index.md) — modern-di's own syntax, end to end.
- [Design decisions](design-decisions.md) — the reasoning behind the API's choices.
