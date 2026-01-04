# Modern DI

Welcome to the `modern-di` documentation!

`modern-di` is a Python dependency injection framework which, among other things,
supports the following:

- Scopes and granular context management
- Python 3.10+ support
- Fully typed and tested
- Integrations with `FastAPI`, `FastStream` and `LiteStar`

---

# Quickstart

## 1. Install `modern-di` using your favorite tool:

If you need only `modern-di` without integrations:

=== "uv"

    ```bash
    uv add modern-di
    ```

=== "pip"

    ```bash
    pip install modern-di
    ```

=== "poetry"

    ```bash
    poetry add modern-di
    ```

If you need to integrate with `fastapi` or `litestar`, then install `modern-di-fastapi` or `modern-di-litestar` accordingly.

## 2. Describe resources and classes:
```python
import dataclasses
import logging
import typing


logger = logging.getLogger(__name__)


def create_singleton() -> str:
    return "some string"


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleFactory:
    dep1: str
    dep2: int


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentFactory:
    singleton: str
```

## 3. Describe dependencies groups

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    singleton = providers.Singleton(Scope.APP, create_singleton)

    simple_factory = providers.Factory(Scope.REQUEST, SimpleFactory, dep1="text", dep2=123)
    dependent_factory = providers.Factory(
        Scope.REQUEST,
        DependentFactory,
        singleton=singleton.cast,
    )
```

## 4.1. Integrate with your framework

For now there are integrations for the following frameworks:

1. [FastAPI](integrations/fastapi)
2. [FastStream](integrations/faststream)
3. [LiteStar](integrations/litestar)

## 4.2. Or use `modern-di` without integrations

Create a container and resolve dependencies in your code
```python
from modern_di import Container, Scope


# For applications that need both sync and async resolution, use AsyncContainer
ALL_GROUPS = [Dependencies]

# Initialize container of app scope
container = Container(groups=ALL_GROUPS)

# Resolve provider
container.resolve_provider(Dependencies.singleton)

# You can also resolve by type if you've registered groups
instance3 = container.sync_resolve(str)  # resolves the singleton

# Create container of request scope
request_container = container.build_child_container(scope=Scope.REQUEST)
# Resolve factories of request scope
container.resolve_provider(Dependencies.simple_factory)
container.resolve_provider(Dependencies.dependent_factory)

# Close container when done
container.close()
```
