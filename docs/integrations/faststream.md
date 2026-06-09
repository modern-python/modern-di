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
import dataclasses
import typing

import faststream
from faststream.nats import NatsBroker
import modern_di_faststream
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    feature_flag: bool = False


@dataclasses.dataclass(kw_only=True, slots=True)
class OrderProcessor:
    settings: Settings        # auto-injected by type

    def process(self, payload: dict) -> dict:
        return {"ok": True, "feature_flag": self.settings.feature_flag}


class AppGroup(Group):
    settings = providers.Factory(
        scope=Scope.APP,
        creator=Settings,
        cache_settings=providers.CacheSettings(),
    )
    order_processor = providers.Factory(
        scope=Scope.REQUEST,
        creator=OrderProcessor,
    )


broker = NatsBroker()
app = faststream.FastStream(broker=broker)

modern_di_faststream.setup_di(app, Container(groups=[AppGroup], validate=True))


@broker.subscriber("orders.in")
async def handle_order(
    payload: dict,
    processor: typing.Annotated[
        OrderProcessor,
        modern_di_faststream.FromDI(OrderProcessor),    # resolve by type
    ],
) -> dict:
    return processor.process(payload)
```

## Scopes

The integration creates a `Scope.REQUEST` child container **for each message** the subscriber receives. REQUEST-scoped providers (and their finalizers) live for the duration of that one message; APP-scoped providers persist for the whole process. At app shutdown, the integration runs `await container.close_async()` on the APP container.

There is no `Scope.SESSION` for FastStream — message brokers don't have a session concept comparable to websockets.

## Framework context objects

`faststream.StreamMessage` is automatically made available by the integration, so factories can declare it as a parameter and get the current message.

The following context provider is also available for explicit import:

- `faststream_message_provider` — provides the current `faststream.StreamMessage` object.

### Implicit (type-based) usage

```python
import faststream
from modern_di import Group, Scope, providers


def create_message_info(message: faststream.StreamMessage) -> dict[str, str]:
    return {
        "message_id": str(message.message_id),
        "processed": str(message.processed),
    }


class AppGroup(Group):
    # The message dependency is resolved by type annotation
    message_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_message_info,
    )
```

### Explicit (provider-based) usage

```python
import faststream
import modern_di_faststream
from modern_di import Group, Scope, providers


def create_message_info(message: faststream.StreamMessage) -> dict[str, str]:
    return {"message_id": str(message.message_id)}


class AppGroup(Group):
    message_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_message_info,
        kwargs={"message": modern_di_faststream.faststream_message_provider},
    )
```

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Wire the APP-scope container into FastStream — creates a REQUEST child container per message and closes the APP container at shutdown. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in subscriber signatures; accepts a provider instance or a plain type. |
| `fetch_di_container(app)` | Returns the APP-scope container registered with the FastStream app. |
| `faststream_message_provider` | `ContextProvider` for the current `faststream.StreamMessage`. |
