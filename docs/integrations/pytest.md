# Usage with `pytest`

`modern-di-pytest` turns DI dependencies into pytest fixtures. It registers no pytest plugin, so
nothing loads on its own: you import its two functions in `conftest.py` or a test module.
`modern_di_fixture` makes one fixture from one dependency, and `expose` makes one fixture per provider
across one or more `Group` subclasses.

You can test without it. Yield a `Container` from your own fixture and call `container.resolve(...)`
in the tests; [Testing with overrides](../recipes/testing-overrides.md) covers swapping in fakes that
way.

## How to use

### 1. Install

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

### 2. Define a `di_container` fixture

The package never builds a container. You own it, and you pick its pytest scope:

<!-- invisible-code-block: python
import sys
import types

from modern_di import Group, Scope, providers


class UserRepo:
    def list_users(self) -> list[str]:
        return []


class FakeRepo(UserRepo):
    def list_users(self) -> list[str]:
        return ["fake"]


class UserService:
    def __init__(self, repo: UserRepo) -> None:
        self._repo = repo

    def list_users(self) -> list[str]:
        return self._repo.list_users()


class EmailClient:
    def send(self, message: str) -> None:
        pass


class Dependencies(Group):
    user_repo = providers.Factory(UserRepo, scope=Scope.APP)
    user_service = providers.Factory(UserService, scope=Scope.APP)


class Auth(Group):
    pass


class Billing(Group):
    email_client_provider = providers.Factory(EmailClient, scope=Scope.APP)


app_module = types.ModuleType("app")
ioc_module = types.ModuleType("app.ioc")
services_module = types.ModuleType("app.services")
fakes_module = types.ModuleType("tests.fakes")
ioc_module.Dependencies = Dependencies
ioc_module.Auth = Auth
ioc_module.Billing = Billing
ioc_module.ALL_GROUPS = [Dependencies, Auth, Billing]
services_module.UserService = UserService
services_module.EmailClient = EmailClient
fakes_module.FakeRepo = FakeRepo
app_module.ioc = ioc_module
app_module.services = services_module
sys.modules.update(
    {"app": app_module, "app.ioc": ioc_module, "app.services": services_module, "tests.fakes": fakes_module}
)
del UserRepo, FakeRepo, UserService, EmailClient, Dependencies, Auth, Billing
-->

```python
import typing

import modern_di
import pytest

from app import ioc


@pytest.fixture(scope="session")
def di_container() -> typing.Iterator[modern_di.Container]:
    with modern_di.Container(groups=ioc.ALL_GROUPS) as container:
        container.validate()  # a broken graph errors every test that uses the container
        yield container
```

If any provider has an async finalizer, make this an async fixture that uses `async with`. A sync
`with` closes the container through `close_sync()`, which cannot await, so teardown raises
[`FinalizerError`](../troubleshooting/finalizer-error.md) wrapping
[`AsyncFinalizerInSyncCloseError`](../troubleshooting/async-finalizer-in-sync-close-error.md).

### 3. Materialize dependencies as fixtures

```python
from modern_di_pytest import expose, modern_di_fixture

from app.ioc import Auth, Billing, Dependencies
from app.services import EmailClient


expose(Dependencies, Auth, Billing)  # one fixture per provider, named after the attribute

email_client = modern_di_fixture(EmailClient)  # one fixture, named after this variable
```

`expose` installs its fixtures onto the module that calls it, found by stack inspection, so call it at
module level in `conftest.py` or a test module, or pass `module=` explicitly. Attributes that are not
providers are skipped. Before installing anything, it raises `ValueError` when two groups share an
attribute name and `TypeError` when called with no groups. It overwrites any module attribute with the
same name as a fixture.

### 4. Use the fixtures in tests

Tests receive resolved dependencies by name:

```python
from app.services import EmailClient, UserService


def test_listing(user_service: UserService) -> None:
    assert user_service.list_users() == []


def test_email(email_client: EmailClient) -> None:
    email_client.send("hi")
```

## Pointing a fixture at a child container

The generated fixtures resolve from `di_container`, an `APP` container, so a `REQUEST`-scoped provider
fails at fixture setup with
[`ScopeNotInitializedError`](../troubleshooting/scope-not-initialized-error.md). Define a child
container fixture and pass its name with `container_fixture=`:

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

`expose` takes `container_fixture=` too. Its fixture names come from the group's attributes, so
exposing the same group against two containers in one module keeps only the second call's fixtures.
Put the two `expose` calls in separate modules.

A fixture's `pytest_scope` cannot be wider than its container fixture's scope. A `"session"` fixture
built on the function-scoped `request_container` fails with pytest's `ScopeMismatch`.

## Overrides

Fixtures resolve during test setup, before the test body runs, so an override set inside the test
comes too late. Apply it in a fixture that the generated fixtures depend on. Redefining `di_container`
in a test module does that for every generated fixture in the module, and the `with` block resets the
override after each test:

```python
import typing

import modern_di
import pytest

from app.ioc import Dependencies
from app.services import UserService
from tests.fakes import FakeRepo


@pytest.fixture
def di_container(di_container: modern_di.Container) -> typing.Iterator[modern_di.Container]:
    with di_container.override(Dependencies.user_repo, FakeRepo()):
        yield di_container


def test_with_fake_repo(user_service: UserService) -> None:
    assert user_service.list_users() == ["fake"]
```

To fake a dependency for some fixtures only, put the override in its own fixture and point those
fixtures at it with `container_fixture=`:

```python
import typing

import modern_di
import pytest
from modern_di_pytest import modern_di_fixture

from app.ioc import Dependencies
from app.services import UserService
from tests.fakes import FakeRepo


@pytest.fixture
def fake_repo_container(
    di_container: modern_di.Container,
) -> typing.Iterator[modern_di.Container]:
    with di_container.override(Dependencies.user_repo, FakeRepo()):
        yield di_container


user_service_with_fake_repo = modern_di_fixture(
    UserService, container_fixture="fake_repo_container"
)


def test_targeted_override(user_service_with_fake_repo: UserService) -> None:
    assert user_service_with_fake_repo.list_users() == ["fake"]
```

<!-- invisible-code-block: python
assert {"user_repo", "user_service", "email_client_provider"} <= globals().keys()

with modern_di.Container(groups=ioc.ALL_GROUPS) as plain_container:
    test_listing(plain_container.resolve(UserService))
    test_email(plain_container.resolve(EmailClient))
    with plain_container.override(Dependencies.user_repo, FakeRepo()):
        test_with_fake_repo(plain_container.resolve(UserService))
        test_targeted_override(plain_container.resolve(UserService))
    test_listing(plain_container.resolve(UserService))

for stand_in in ("app", "app.ioc", "app.services", "tests.fakes"):
    sys.modules.pop(stand_in)
-->

With a session-scoped `di_container`, watch cached providers (`cache=True`). A cached instance keeps
the dependencies it was built with. If an earlier test resolved it, a later override of one of its
dependencies does not reach it; if it was first resolved under an override, it keeps the fake after
the override ends. Override the cached provider itself, or give the tests that need the fake a
function-scoped container.

For transactional database sessions and other patterns, see
[Testing with overrides](../recipes/testing-overrides.md).

## See also

- [Testing with overrides](../recipes/testing-overrides.md): override patterns beyond fixtures.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model behind child container fixtures.
- [FinalizerError](../troubleshooting/finalizer-error.md): closing a container with async finalizers.

## API

| Symbol | Description |
|---|---|
| `modern_di_fixture(dependency, *, container_fixture="di_container", name=None, pytest_scope="function")` | Returns a pytest fixture that resolves `dependency` (a type or a provider) through `container.resolve_dependency` on the container fixture. Assign it to a module-level name; `name=` overrides the fixture name. |
| `expose(*groups, container_fixture="di_container", pytest_scope="function", module=None)` | Installs one fixture per provider attribute of each group onto the calling module, or onto `module=`. Raises `ValueError` on a duplicate name across groups and `TypeError` with no groups, before installing anything. |
