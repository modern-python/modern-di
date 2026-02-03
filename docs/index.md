# Modern DI

Welcome to the `modern-di` documentation!

`modern-di` is a Python dependency injection framework which, among other things,
supports the following:

- Automatic dependencies graph based on type annotations
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
    simple_factory: SimpleFactory
    singleton: str
```

## 3. Describe dependencies groups

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=create_singleton,
        cache_settings=providers.CacheSettings()
    )

    # relation between dependent_factory and simple_factory will be defined based on type annotations
    simple_factory = providers.Factory(
        scope=Scope.REQUEST,
        creator=SimpleFactory,
        kwargs={"dep1": "text", "dep2": 123}
    )
    dependent_factory = providers.Factory(
        scope=Scope.REQUEST,
        creator=DependentFactory,
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


ALL_GROUPS = [Dependencies]

# Initialize container of app scope
container = Container(groups=ALL_GROUPS)

# Resolve provider
instance1 = container.resolve_provider(Dependencies.singleton)

# You can also resolve by type if you've registered groups
instance2 = container.resolve(dependency_type=str)  # resolves the singleton

# Create container of request scope
request_container = container.build_child_container(scope=Scope.REQUEST)
try:
    # Resolve factories of request scope
    instance3 = request_container.resolve_provider(Dependencies.simple_factory)
    instance4 = request_container.resolve_provider(Dependencies.dependent_factory)
    # Use your instances...
finally:
    # Close container when done
    # For async usage:
    await request_container.close_async()

    # For sync usage:
    request_container.close_sync()
```
