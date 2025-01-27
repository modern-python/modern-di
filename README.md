"Modern-DI"
==

| Project            | Badges                                                                                                                                                                                                                                                                                          |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| common             | [![MyPy Strict](https://img.shields.io/badge/mypy-strict-blue)](https://mypy.readthedocs.io/en/stable/getting_started.html#strict-mode-and-configuration) [![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di)](https://github.com/modern-python/modern-di/stargazers) |
| modern-di          | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di.svg)](https://pypi.python.org/pypi/modern-di ) [![downloads](https://img.shields.io/pypi/dm/modern-di.svg)](https://pypistats.org/packages/modern-di)                                                                   |
| modern-di-fastapi  | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-fastapi.svg)](https://pypi.python.org/pypi/modern-di-fastapi) [![downloads](https://img.shields.io/pypi/dm/modern-di-fastapi.svg)](https://pypistats.org/packages/modern-di-fastapi)                                    |
| modern-di-litestar | [![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-litestar.svg)](https://pypi.python.org/pypi/modern-di-litestar) [![downloads](https://img.shields.io/pypi/dm/modern-di-litestar.svg)](https://pypistats.org/packages/modern-di-litestar)                                |

Dependency injection framework for Python inspired by `dependency-injector` and `dishka`.

It is in development state yet and gives you the following:
- DI framework with IOC-container and scopes.
- Async and sync resolving.
- Python 3.10-3.13 support.
- Full coverage by types annotations (mypy in strict mode).
- Overriding dependencies for tests.
- Package with zero dependencies.
- Integration with FastAPI and LiteStar
- Thread-safe and asyncio concurrency safe providers

📚 [Documentation](https://modern-di.readthedocs.io)
