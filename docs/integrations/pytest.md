# Usage with `pytest`

`modern-di-pytest` turns any DI dependency into a pytest fixture. Two
callables cover the entire surface — `modern_di_fixture` for a single
dependency and `expose` for bulk-generating one fixture per provider in a
`Group`.

## How to use

1. Install `modern-di-pytest`:

=== "uv"

      ```bash
      uv add --dev modern-di-pytest
      ```

=== "pip"

      ```bash
      pip install modern-di-pytest
      ```

=== "poetry"

      ```bash
      poetry add --group dev modern-di-pytest
      ```

2. Define a `di_container` fixture at the highest pytest scope you want.
   The plugin never builds the container — you own it:

```python
import typing

import modern_di
import pytest

from app import ioc


@pytest.fixture(scope="session")
def di_container() -> typing.Iterator[modern_di.Container]:
    with modern_di.Container(groups=ioc.ALL_GROUPS) as container:
        yield container
```

3. Materialize dependencies as fixtures, either in bulk via `expose` or
   one-by-one via `modern_di_fixture`:

```python
from modern_di_pytest import expose, modern_di_fixture

from app.ioc import Dependencies
from app.services import EmailClient


# Bulk: every Provider on Dependencies becomes a pytest fixture
# named after the class attribute. Non-Provider attributes are skipped.
expose(Dependencies)

# Manual: a single type or Provider as a named fixture.
email_client = modern_di_fixture(EmailClient)
```

4. Tests receive resolved dependencies by name:

```python
from app.services import EmailClient, UserService


def test_listing(user_service: UserService) -> None:
    assert user_service.list_users() == []


def test_email(email_client: EmailClient) -> None:
    email_client.send("hi")
```

## Pointing a fixture at a child container

Define the child-container fixture yourself, then pass its name via
`container_fixture=`:

```python
import typing

import modern_di
import pytest
from modern_di_pytest import modern_di_fixture

from app.services import UserService


@pytest.fixture
def request_container(
    di_container: modern_di.Container,
) -> typing.Iterator[modern_di.Container]:
    with di_container.build_child_container(scope=modern_di.Scope.REQUEST) as container:
        yield container


request_user_service = modern_di_fixture(
    UserService, container_fixture="request_container"
)
```

The same `container_fixture=` parameter is also accepted by `expose`, so a
whole `Group` can be exposed against the request container.

## Overrides

`modern-di-pytest` deliberately does **not** ship override sugar. Use
`Container.override()` directly — it is already backed by a tree-shared
`OverridesRegistry`:

```python
import modern_di

from app.ioc import Dependencies
from app.services import UserService
from tests.fakes import FakeRepo


def test_with_override(
    di_container: modern_di.Container,
    user_service: UserService,
) -> None:
    di_container.override(Dependencies.user_repo, FakeRepo())
    try:
        assert user_service.list_users() == []
    finally:
        di_container.reset_override(Dependencies.user_repo)
```

When `di_container` is session-scoped, prefer to wrap the override in a
function-scoped fixture so cleanup is guaranteed:

```python
import typing

import modern_di
import pytest

from app.ioc import Dependencies
from tests.fakes import FakeRepo


@pytest.fixture
def mock_user_repo(di_container: modern_di.Container) -> typing.Iterator[None]:
    di_container.override(Dependencies.user_repo, FakeRepo())
    yield
    di_container.reset_override(Dependencies.user_repo)
```
