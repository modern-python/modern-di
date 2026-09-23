# Usage with `FastStream`

## How to use

### 1. Install `modern-di-faststream`

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

### 2. Apply to your application

```python
import dataclasses
import typing

import faststream
from faststream.nats import NatsBroker
import modern_di_faststream
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings   # APP-scoped, injected by type

    def as_dict(self) -> dict[str, str]:
        return {"service": self.settings.service_name}


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


broker = NatsBroker()
app = faststream.FastStream(broker=broker)
container = Container(groups=[AppGroup])
modern_di_faststream.setup_di(app, container)
container.validate()  # after setup_di — its connection providers are now registered


@broker.subscriber("orders.in")
async def handle_order(
    report: typing.Annotated[Report, modern_di_faststream.FromDI(Report)],
) -> dict[str, str]:
    return report.as_dict()
```

### Several brokers

`setup_di` covers every broker of the app, not only the first. The DI middleware is installed
by an `on_startup` hook that walks `app.brokers`, so a broker passed to `FastStream(...)` and
one added with `app.add_broker` after `setup_di` are treated the same:

```python
app = faststream.FastStream(nats_broker)
modern_di_faststream.setup_di(app, container)
app.add_broker(kafka_broker)  # also gets the DI middleware at startup
```

A broker created inside an `on_startup` hook is covered as well, since `setup_di` no longer
needs a broker at call time. Hooks run in registration order, so register that hook **before**
calling `setup_di`; otherwise the install step runs first and does not see the broker. If the
app still has no broker when the install step runs, it raises a `RuntimeError` naming both
remedies.

```python
app = faststream.FastStream()


@app.on_startup
async def attach_broker() -> None:
    app.add_broker(NatsBroker(settings.nats_url))


modern_di_faststream.setup_di(app, container)  # after the hook, so startup sees the broker
```

Between `setup_di` and startup no broker carries the middleware yet; see
[Testing](#testing) for the one place that shows.

## Scopes

The integration creates a `Scope.REQUEST` child container **for each message** the subscriber receives. REQUEST-scoped providers (and their finalizers) live for the duration of that one message; APP-scoped providers persist for the whole process. At app shutdown, the integration runs `await container.close_async()` on the APP container.

There is no `Scope.SESSION` for FastStream — message brokers don't have a session concept comparable to websockets.

## Framework context objects

`faststream.StreamMessage` is automatically made available by the integration, so factories can declare it as a parameter and get the current message — see [Framework Context Objects](../providers/context.md#framework-context-objects) for how implicit and explicit resolution work.

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
        create_message_info,
        scope=Scope.REQUEST,
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
        create_message_info,
        scope=Scope.REQUEST,
        kwargs={"message": modern_di_faststream.faststream_message_provider},
    )
```

## Testing

!!! warning "Pair the test broker with `TestApp` in the same `with` statement"
    When testing DI-using subscribers, pair the test broker (`TestNatsBroker`,
    etc.) with `TestApp` in the **same** `with` / `async with` statement.
    FastStream's `TestBroker` decides whether to run app `on_startup` hooks by
    inspecting that statement; `async with TestNatsBroker(broker):` alone
    starts the broker without running `on_startup`. The integration installs
    its middleware and reopens the container in those hooks, so a `FromDI`
    subscriber reached this way has no request container and raises a
    `RuntimeError` that names `setup_di` and `TestApp` as the fix.

    ```python
    async with TestNatsBroker(broker) as br, TestApp(app):
        await br.publish(...)
    ```

## See also

- [Testing with overrides](../recipes/testing-overrides.md) — swap providers in your tests.
- [Async resources via lifespan](../recipes/async-lifespan.md) — constructing async resources with finalizers.
- [Lifecycle](../providers/lifecycle.md) — finalizers and `close_async()`.
- [Scopes](../providers/scopes.md) — the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Wire the APP-scope container into FastStream — at startup, installs the middleware that creates a REQUEST child container per message on every broker of the app, and raises `RuntimeError` if there is none by then; closes the APP container at shutdown. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in subscriber signatures; accepts a provider instance or a plain type. Raises `RuntimeError` naming `setup_di` when a message reaches it without the middleware installed. |
| `fetch_di_container(app)` | Returns the APP-scope container registered with the FastStream app. |
| `faststream_message_provider` | `ContextProvider` for the current `faststream.StreamMessage`. |
