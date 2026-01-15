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
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=create_singleton,
        cache_settings=providers.CacheSettings()
    )


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

## Framework Context Objects

Framework-specific context objects like `faststream.StreamMessage` are automatically provided by the integration, so you don't need to explicitly define ContextProviders for these objects in your dependency groups.

For example, to use the message object in a factory:

```python
import faststream
from modern_di import Group, Scope, providers

def create_message_info(message: faststream.StreamMessage) -> dict[str, str]:
    return {
        "message_id": str(message.message_id),
        "processed": str(message.processed),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory uses the message from context (automatically provided by the integration)
    message_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_message_info,
    )
```
