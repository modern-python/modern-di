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

Framework-specific context objects like `faststream.StreamMessage` are automatically made available by the integration.
You can reference these context providers in your factories either implicitly through type annotations or explicitly by importing them.

The following context provider is available for import:
- `faststream_message_provider` - Provides the current `faststream.StreamMessage` object

### Implicit Usage (Type-based Resolution)

In many cases, you can rely on automatic dependency resolution based on type annotations:

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
    # Factory automatically resolves the message dependency based on type annotation
    message_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_message_info,
    )
```

### Explicit Usage (Provider-based Resolution)

For more control, you can explicitly reference the context provider:

```python
import faststream
import modern_di_faststream
from modern_di import Group, Scope, providers

def create_message_info(message: faststream.StreamMessage) -> dict[str, str]:
    return {
        "message_id": str(message.message_id),
        "processed": str(message.processed),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory explicitly uses the message provider from the integration
    message_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_message_info,
        kwargs={"message": modern_di_faststream.faststream_message_provider}
    )
```
