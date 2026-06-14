# Testing with overrides

**Problem.** Tests need to swap a real dependency (database, HTTP client, clock) for a fake one without touching production wiring.

## Solution

`container.override(provider, replacement)` replaces what the provider resolves to. The replacement is keyed by **provider reference** (not name) and is shared across the container tree, so an override on the root APP container applies to all child REQUEST containers too. Reset with `container.reset_override(provider)` (or `container.reset_override()` to clear all).

## Pattern 1: Simple mock override

For unit-style tests, override the provider with a fake before exercising the code under test:

```python
from unittest.mock import AsyncMock
import pytest

from app.ioc import Dependencies, container


@pytest.fixture
def fake_users() -> AsyncMock:
    fake = AsyncMock(spec=UserRepository)
    container.override(Dependencies.user_repository, fake)
    yield fake
    container.reset_override(Dependencies.user_repository)


async def test_place_order_calls_users(fake_users: AsyncMock) -> None:
    use_case = container.resolve(PlaceOrder)
    await use_case.run(...)
    fake_users.find_by_id.assert_awaited()
```

## Pattern 2: Transactional session fixture (real database)

For integration tests against a real database, run each test in a nested transaction that rolls back at the end. Override the engine provider with the test connection so every session created during the test reuses it.

```python
import pytest
import sqlalchemy.ext.asyncio as sa_async

from app.ioc import Dependencies, container


@pytest.fixture(scope="session")
async def engine() -> sa_async.AsyncEngine:
    eng = sa_async.create_async_engine("postgresql+asyncpg://...test")
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def db_connection(engine: sa_async.AsyncEngine) -> sa_async.AsyncConnection:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        container.override(Dependencies.engine, connection)
        try:
            yield connection
        finally:
            container.reset_override(Dependencies.engine)
            await transaction.rollback()
```

Tests that pull a session through DI (`container.resolve(sa_async.AsyncSession)`) get one bound to the test connection, and everything they write rolls back at the end.

## Pattern 3: `modern-di-pytest` fixtures

For tests that consume DI dependencies as fixtures rather than resolving manually, the `modern-di-pytest` package generates fixtures from providers:

```python
from modern_di_pytest import expose, modern_di_fixture

from app.ioc import Dependencies


# Single fixture from a specific provider
user_repository = modern_di_fixture(Dependencies.user_repository)

# Or expose every provider in a Group as a fixture (one per attribute)
expose(Dependencies)


async def test_user_repo(user_repository: UserRepository) -> None:
    assert await user_repository.count() == 0
```

Combine with `container.override(...)` in a setup fixture to swap underlying providers — `modern_di_fixture` resolves through the override.

## Pitfalls

- **Overrides are global.** Override the root APP container and every child REQUEST container sees the replacement. Fine in tests; remember it if you also override in production code.
- **`override` is keyed by provider reference.** Pass `Dependencies.user_repository` (the provider object), not the string `"user_repository"`.
- **Always `reset_override` in the fixture teardown.** Leaking overrides between tests is a class of bug that doesn't fail loudly.
- **Override the right level.** If you override the engine but tests resolve the session, the session's creator still runs — make sure the engine override produces something the creator can use. If the test relies on a specific session, override the session directly.

## See also

- [Pytest integration](../integrations/pytest.md) and [Testing: fixtures](../testing/fixtures.md).
- [Async SQLAlchemy recipe](sqlalchemy.md) — the engine/session/repository chain being overridden here.
- Reference template: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template) — full transactional fixture setup.
