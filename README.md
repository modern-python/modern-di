# modern-di

[![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di)](https://github.com/modern-python/modern-di/stargazers)
[![Context7](https://img.shields.io/badge/Context7-docs-blue)](https://context7.com/modern-python/modern-di)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

| Project                                                                         | Badges                                                                                                                                                                                                                                                                   |
|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| modern-di                                                                       | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di.svg)](https://pypi.python.org/pypi/modern-di ) [![downloads](https://static.pepy.tech/badge/modern-di/month)](https://pepy.tech/projects/modern-di)                                            |
| [modern-di-fastapi](https://github.com/modern-python/modern-di-fastapi)         | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-fastapi.svg)](https://pypi.python.org/pypi/modern-di-fastapi) [![downloads](https://static.pepy.tech/badge/modern-di-fastapi/month)](https://pepy.tech/projects/modern-di-fastapi)             |
| [modern-di-faststream  ](https://github.com/modern-python/modern-di-faststream) | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-faststream.svg)](https://pypi.python.org/pypi/modern-di-faststream) [![downloads](https://static.pepy.tech/badge/modern-di-faststream/month)](https://pepy.tech/projects/modern-di-faststream) |
| [modern-di-litestar ](https://github.com/modern-python/modern-di-litestar)      | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-litestar.svg)](https://pypi.python.org/pypi/modern-di-litestar) [![downloads](https://static.pepy.tech/badge/modern-di-litestar/month)](https://pepy.tech/projects/modern-di-litestar)         |
| [modern-di-typer](https://github.com/modern-python/modern-di-typer)            | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-typer.svg)](https://pypi.python.org/pypi/modern-di-typer) [![downloads](https://static.pepy.tech/badge/modern-di-typer/month)](https://pepy.tech/projects/modern-di-typer)                     |
| [modern-di-pytest](https://github.com/modern-python/modern-di-pytest)          | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-pytest.svg)](https://pypi.python.org/pypi/modern-di-pytest) [![downloads](https://static.pepy.tech/badge/modern-di-pytest/month)](https://pepy.tech/projects/modern-di-pytest)                 |

`modern-di` is a python dependency injection framework which supports the following:

- Automatic dependency graph based on type annotations
- Also, explicit dependencies are allowed where needed
- Scopes and context management
- Python 3.10+ support
- Fully typed and tested
- Integrations with `FastAPI`, `FastStream`, `LiteStar` and `Typer`
- Pytest integration (`modern-di-pytest`) — turns any DI dependency into a pytest fixture

## Install

```bash
uv add modern-di      # or: pip install modern-di
```

## Quick Start

```python
import dataclasses
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"


@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    settings: Settings  # auto-injected by type


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)
    user_repository = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)


with Container(groups=[Dependencies], validate=True) as container:
    with container.build_child_container(scope=Scope.REQUEST) as request:
        repo = request.resolve(UserRepository)
        print(repo.settings.database_url)
```

See the [documentation](https://modern-di.modern-python.org) for scopes, lifecycles, finalizers, and framework integrations.

Usage examples:

- with LiteStar - [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- with FastAPI - [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)

## 📚 [Documentation](https://modern-di.modern-python.org)

## 📦 [PyPI](https://pypi.org/project/modern-di)

## 📝 [License](LICENSE)

## Part of `modern-python`

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python) — see the org profile for the categorized index.
