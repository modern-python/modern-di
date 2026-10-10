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
app = faststream.FastStream(broker)
container = Container(groups=[AppGroup])
modern_di_faststream.setup_di(app, container)
container.validate()  # after setup_di: its context provider is now registered


@broker.subscriber("orders.in")
async def handle_order(
    report: typing.Annotated[Report, modern_di_faststream.FromDI(Report)],
) -> dict[str, str]:
    return report.as_dict()
```

`setup_di` takes a `faststream.FastStream` or an `AsgiFastStream` app. It registers the
message context provider, installs a middleware on every broker of the app at startup that
builds a `Scope.REQUEST` child container per message, and closes the root container at
shutdown.

## Scopes

The integration creates a `Scope.REQUEST` child container for each message a subscriber
receives. REQUEST-scoped providers and their finalizers live for that one message. The
child is closed with `close_async()`, so finalizers may be async or sync. Resolution itself
is synchronous, as everywhere in modern-di.

There is no `Scope.SESSION` for FastStream: message brokers don't have a session concept
comparable to websockets.

## Root container lifecycle

`setup_di` registers two `on_startup` hooks: one opens the root container and the next
installs the middleware on every broker. An `after_shutdown` hook closes the root with
`close_async()`, which runs APP-scoped finalizers. Because startup reopens the container,
an app that stops and starts again on the same container works.

## Framework context objects

`faststream.StreamMessage` is automatically made available by the integration, so factories can declare it as a parameter and get the current message. See [Framework context objects](../providers/context.md#framework-context-objects) for how implicit and explicit resolution work.

The following context provider is also available for explicit import:

- `faststream_message_provider` provides the current `faststream.StreamMessage` object.

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

The middleware is installed and the container reopened by the app's `on_startup` hooks,
and FastStream's `TestApp` is what runs them. Enter the test broker first and `TestApp`
after it, either in one `async with` statement or with `TestApp` nested inside:

```python
from faststream import TestApp
from faststream.nats import TestNatsBroker



async def test_handle_order() -> None:
    async with TestNatsBroker(broker) as test_broker, TestApp(app):
        response = await test_broker.request({"order_id": 1}, "orders.in")
        assert await response.decode() == {"service": "catalog"}
```

<!-- invisible-code-block: python
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)  # TestNatsBroker cannot parse a Markdown file's AST
    await test_handle_order()
-->

A test broker without `TestApp` runs no startup hook, so a `FromDI` subscriber finds no
request container and raises a `RuntimeError` that names `setup_di` and `TestApp`.
Entering `TestApp` before the test broker makes the app connect to the real broker.

## Several brokers

`setup_di` covers every broker of the app, not only the first. The DI middleware is installed
by an `on_startup` hook that walks `app.brokers`, so a broker passed to `FastStream(...)` and
one added with `app.add_broker` after `setup_di` are treated the same:

<!-- clear-namespace -->

<!-- invisible-code-block: python
import faststream
import modern_di_faststream
from faststream.kafka import KafkaBroker
from faststream.nats import NatsBroker
from modern_di import Container

container = Container()
nats_broker = NatsBroker()
kafka_broker = KafkaBroker()
-->

```python
app = faststream.FastStream(nats_broker)
modern_di_faststream.setup_di(app, container)
app.add_broker(kafka_broker)  # also gets the DI middleware at startup
```

A broker created inside an `on_startup` hook is covered as well, since `setup_di` doesn't need a
broker at call time. Hooks run in registration order, so register that hook **before**
calling `setup_di`; otherwise the install step runs first and does not see the broker. If the
app still has no broker when the install step runs, it raises a `RuntimeError` naming both
remedies.

<!-- clear-namespace -->

<!-- invisible-code-block: python
import faststream
import modern_di_faststream
from faststream.nats import NatsBroker
from modern_di import Container

container = Container()
-->

```python
app = faststream.FastStream()


@app.on_startup
async def attach_broker() -> None:
    app.add_broker(NatsBroker())


modern_di_faststream.setup_di(app, container)  # after the hook, so startup sees the broker
```

Between `setup_di` and startup no broker carries the middleware yet; see
[Testing](#testing) for the one place that shows.

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Async resources via lifespan](../recipes/async-lifespan.md): constructing async resources with finalizers.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Wire the APP-scope container into FastStream: at startup, installs the middleware that creates a REQUEST child container per message on every broker of the app, and raises `RuntimeError` if there is none by then; closes the APP container at shutdown. |
| `FromDI(dependency, *, use_cache=True, cast=False)` | A `faststream.Depends` wrapper for `Annotated[T, FromDI(...)]` in subscriber signatures; accepts a provider instance or a plain type. `use_cache` and `cast` are passed through to `faststream.Depends`. Raises `RuntimeError` naming `setup_di` when a message reaches it without the middleware installed. |
| `fetch_di_container(app)` | Returns the APP-scope container registered with the FastStream app. |
| `faststream_message_provider` | `ContextProvider` for the current `faststream.StreamMessage`. |
