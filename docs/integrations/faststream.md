# Usage with `FastStream`

## How to use

1. Install `modern-di-faststream`:

=== "uv"

      ```bash
      uv add modern-di-faststream
      ```

=== "pip"

      ```bash
      pip install modern-di-faststream
      ```

=== "poetry"

      ```bash
      poetry add modern-di-faststream
      ```

2. Apply this code example to your application:

```python
import datetime
import typing

import faststream
from faststream.nats import NatsBroker
import modern_di_faststream
from modern_di import Scope, providers


broker = NatsBroker()
app = faststream.FastStream(broker=broker)
modern_di_faststream.setup_di(app)


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    # async resource initiated
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        pass  # async resource destructed


async_resource = providers.Resource(Scope.APP, create_async_resource)


@broker.subscriber("in")
async def read_root(
    instance: typing.Annotated[
        datetime.datetime,
        modern_di_faststream.FromDI(async_resource),
    ],
) -> datetime.datetime:
    return instance

```
