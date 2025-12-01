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
from modern_di import Group, Scope, providers


broker = NatsBroker()
app = faststream.FastStream(broker=broker)


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    # async resource initiated
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        pass  # async resource destructed


class AppGroup(Group):
    async_resource = providers.Resource(Scope.APP, create_async_resource)


# Register your groups
ALL_GROUPS = [AppGroup]

# Setup DI with your groups
modern_di_faststream.setup_di(app, groups=ALL_GROUPS)


@broker.subscriber("in")
async def read_root(
    instance: typing.Annotated[
        datetime.datetime,
        modern_di_faststream.FromDI(datetime.datetime),  # Resolve by type instead of provider
    ],
) -> datetime.datetime:
    return instance

```
