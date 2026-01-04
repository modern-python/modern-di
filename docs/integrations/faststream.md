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
from modern_di import Container, Group, Scope, providers


broker = NatsBroker()
app = faststream.FastStream(broker=broker)


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Singleton(Scope.APP, create_singleton)


# Register your groups
ALL_GROUPS = [AppGroup]

# Setup DI with your groups
modern_di_faststream.setup_di(app, Container(groups=ALL_GROUPS))


@broker.subscriber("in")
async def read_root(
    instance: typing.Annotated[
        datetime.datetime,
        modern_di_faststream.FromDI(datetime.datetime),  # Resolve by type instead of provider
    ],
) -> datetime.datetime:
    return instance

```
