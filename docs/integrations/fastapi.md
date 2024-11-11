# Usage with `Fastapi`

*More advanced example of usage with FastAPI - [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)*

1. Install `modern-di-fastapi` package from PYPI: `uv add modern-di-fastapi` or `pip install modern-di-fastapi`, etc.
2. Apply this code example to your application:
```python
import datetime
import contextlib
import typing

import fastapi
import modern_di_fastapi
from modern_di import Scope, providers


@contextlib.asynccontextmanager
async def lifespan_manager(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    async with modern_di_fastapi.fetch_di_container(app_):
        yield


app = fastapi.FastAPI(lifespan=lifespan_manager)
modern_di_fastapi.setup_di(app)


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    # async resource initiated
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        pass  # async resource destructed


async_resource = providers.Resource(Scope.APP, create_async_resource)


@app.get("/")
async def read_root(
        instance: typing.Annotated[
            datetime.datetime,
            modern_di_fastapi.FromDI(async_resource),
        ],
) -> datetime.datetime:
    return instance

```
