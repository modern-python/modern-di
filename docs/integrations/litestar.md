# Usage with `Litestar`

*More advanced example of usage with LiteStar - [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)*

1. Install `modern-di-litestar` package from PYPI: `uv add modern-di-litestar` or `pip install modern-di-litestar`, etc.
2. Apply this code example to your application:
```python
import contextlib
import datetime
import typing

from litestar import Litestar, get
import modern_di_litestar
from modern_di import Scope, providers


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    # async resource initiated
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        pass  # async resource destructed


async_resource = providers.Resource(Scope.APP, create_async_resource)


@get("/", dependencies={"injected": modern_di_litestar.FromDI(async_resource)})
async def index(injected: datetime.datetime) -> str:
    return injected.isoformat()


@contextlib.asynccontextmanager
async def lifespan_manager(app_: Litestar) -> typing.AsyncIterator[None]:
    async with modern_di_litestar.fetch_di_container(app_):
        yield


app = Litestar(
    route_handlers=[index],
    dependencies={**modern_di_litestar.prepare_di_dependencies()},
    lifespan=[lifespan_manager],
)
modern_di_litestar.setup_di(app)
```
