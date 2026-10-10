# Usage with `aiogram`

aiogram passes handler arguments by name from its middleware data, but it has no typed
provider graph. `modern-di-aiogram` adds one: mark handler parameters with `FromDI` and
decorate the handler with `@inject`, or pass `auto_inject=True` to skip the decorator.
`setup_di` builds a `Scope.REQUEST` child container per update and opens and closes the root
container with the dispatcher.

## How to use

### 1. Install `modern-di-aiogram`

=== "uv"

    ```bash
    uv add modern-di-aiogram
    ```

=== "pip"

    ```bash
    pip install modern-di-aiogram
    ```

=== "poetry"

    ```bash
    poetry add modern-di-aiogram
    ```

### 2. Apply to your application

```python
import dataclasses
import typing

from aiogram import Dispatcher
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers
from modern_di_aiogram import FromDI, inject, setup_di


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


dispatcher = Dispatcher()
container = Container(groups=[AppGroup])
setup_di(dispatcher, container)
container.validate()  # after setup_di: its context providers are now registered


@dispatcher.message()
@inject
async def greet(
    message: Message,
    report: typing.Annotated[Report, FromDI(Report)],
) -> None:
    await message.answer(str(report.as_dict()))
```

<!-- invisible-code-block: python
report_settings, report_group = Settings, AppGroup
-->

## Scopes

The integration creates one `Scope.REQUEST` child container per update. Its middleware is an
[outer middleware](https://docs.aiogram.dev/en/latest/dispatcher/middlewares.html) on
`dispatcher.update`, so it wraps every update whichever router or handler processes it. The
child is closed with `close_async()` after the handler returns or raises, so REQUEST-scoped
finalizers may be async or sync. Resolution itself is synchronous, as everywhere in modern-di.

There is no `Scope.SESSION` for aiogram: each Telegram update is handled
independently; there's no persistent per-chat/per-user connection comparable
to a WebSocket. See [the scope hierarchy](../providers/scopes.md#what-each-scope-is-for).

## Root container lifecycle

`setup_di` registers `container.open` on `dispatcher.startup` and `container.close_async` on
`dispatcher.shutdown`, and closing runs APP-scoped finalizers. `start_polling()` emits both
events, and so does an aiohttp app wired with aiogram's `setup_application()`.

## Framework context objects

Two types resolve by annotation: `aiogram.types.Update` and `aiogram.types.TelegramObject`,
the concrete event unwrapped from the update. See
[Framework context objects](../providers/context.md#framework-context-objects) for how
implicit and explicit resolution work.

The following context providers are also available for explicit import:

- `aiogram_update_provider` provides the current `aiogram.types.Update`.
- `aiogram_event_provider` provides the current `aiogram.types.TelegramObject`,
  the concrete event unwrapped from the `Update` (e.g. a `Message` or
  `CallbackQuery` instance).

A concrete event type such as `Message` has no provider of its own, so a factory that
declares `message: Message` fails `container.validate()`. Annotate the parameter as
`TelegramObject`, or wire it to `aiogram_event_provider` with `kwargs`.

### Implicit (type-based) usage

```python
from aiogram.types import TelegramObject, Update
from modern_di import Group, Scope, providers


def create_update_info(update: Update, event: TelegramObject) -> dict[str, str]:
    return {
        "update_id": str(update.update_id),
        "event_type": type(event).__name__,
    }


class AppGroup(Group):
    # Update and TelegramObject are resolved by type annotation
    update_info = providers.Factory(
        create_update_info,
        scope=Scope.REQUEST,
    )
```

### Explicit (provider-based) usage

`aiogram_event_provider` is bound to the base `TelegramObject` type. To get the event
typed as `Message`, wire the provider explicitly. In a factory that is `kwargs`:

```python
from aiogram.types import Message
from modern_di_aiogram import aiogram_event_provider


def message_text(message: Message) -> str:
    return message.text or ""


class AppGroup(Group):
    text = providers.Factory(
        message_text,
        scope=Scope.REQUEST,
        kwargs={"message": aiogram_event_provider},
    )
```

In a handler it is `FromDI`:

```python
import typing

from aiogram.types import Message
from modern_di_aiogram import FromDI, aiogram_event_provider, inject


@inject
async def log_message(
    message: Message,
    same_message: typing.Annotated[Message, FromDI(aiogram_event_provider)],
) -> None:
    assert message is same_message
```

## Auto-injecting handlers

Passing `auto_inject=True` to `setup_di` wraps every handler already
registered on the dispatcher with `@inject` automatically, so individual
handlers don't need the decorator:

```python
import typing

from aiogram import Dispatcher, Router
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers
from modern_di_aiogram import FromDI, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)


router = Router()


@router.message()
async def greet(
    message: Message,
    settings: typing.Annotated[Settings, FromDI(AppGroup.settings)],
) -> None:
    await message.answer(f"{settings.greeting}, {message.from_user.first_name}")


dispatcher = Dispatcher()
dispatcher.include_router(router)
container = Container(groups=[AppGroup])
setup_di(dispatcher, container, auto_inject=True)
container.validate()  # after setup_di: its context providers are now registered
```

!!! warning "Register handlers before startup"
    `auto_inject` wraps handlers on `dispatcher.startup`, which fires from
    `dispatcher.emit_startup()`, the call `start_polling()` makes before serving
    updates. Only handlers registered (via `dispatcher.include_router()` or the
    decorators directly) **before** `emit_startup()` runs are wrapped. A handler
    added afterward is called without injection, so aiogram raises `TypeError`
    for its missing `FromDI` argument.

Handlers on `update` observers (`@dispatcher.update()` or `@router.update()`) are never
wrapped. Decorate those with `@inject` yourself.

## Usage with `aiogram-dialog`

[aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) runs inside
aiogram's dispatch, so the per-update child container that `setup_di`'s
middleware already builds is reachable from dialog code. `modern_di_aiogram.dialog`
adds a dialog-aware `inject` for getters and callbacks (`on_click`,
`on_start`/`on_close`, `on_process_result`). Install it with the normal
`setup_di(...)` and decorate your dialog functions:

```python
import typing

from aiogram_dialog import DialogManager
from modern_di import Group, Scope, providers
from modern_di_aiogram.dialog import FromDI, inject


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)


@inject
async def getter(
    dialog_manager: DialogManager,
    settings: typing.Annotated[Settings, FromDI(Settings)],   # resolve by type
    **kwargs: typing.Any,                                     # required by aiogram-dialog
) -> dict[str, str]:
    return {"greeting": settings.greeting}


@inject
async def on_click(
    callback: typing.Any,
    button: typing.Any,
    manager: DialogManager,
    settings: typing.Annotated[Settings, FromDI(Settings)],
) -> None:
    await manager.done(result=settings.greeting)
```

The container is found by call shape: a getter receives it via
`**manager.middleware_data` (aiogram-dialog calls `getter(**middleware_data)`),
and a callback via the positional `DialogManager`'s `.middleware_data`. Dialog DI
requires the normal `setup_di(dispatcher, container)`, whose middleware provides
the per-update container.

- `modern_di_aiogram.dialog` has no runtime dependency on `aiogram-dialog`;
  install `aiogram-dialog` yourself.
- The `FromDI` marker is the same one used for handlers; it is re-exported from
  `modern_di_aiogram.dialog` for convenience.
- An `@inject` getter must still declare `**kwargs` (aiogram-dialog always calls
  getters with the full `middleware_data`), and a `FromDI` getter parameter must
  not share a name with a `middleware_data` key (e.g. `bot`, `event`).

## Testing

Drive a real `Dispatcher` with a bot that has a fake token: emit startup, feed it an
`Update`, and emit shutdown. `feed_update` returns what the handler returned, so a handler
that returns a value is easy to assert on.

<!-- invisible-code-block: python
Settings, AppGroup = report_settings, report_group
-->

```python
import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update
from modern_di_aiogram import FromDI, inject, setup_di


async def test_report() -> None:
    dispatcher = Dispatcher()
    container = Container(groups=[AppGroup])
    setup_di(dispatcher, container)

    @dispatcher.message()
    @inject
    async def report_handler(
        message: Message,
        report: typing.Annotated[Report, FromDI(Report)],
    ) -> dict[str, str]:
        return report.as_dict()

    bot = Bot("123456:" + "A" * 35)
    update = Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.datetime.now(tz=datetime.UTC),
            chat=Chat(id=1, type="private"),
            text="report",
        ),
    )
    await dispatcher.emit_startup(bot=bot)
    assert await dispatcher.feed_update(bot, update) == {"service": "catalog"}
    await dispatcher.emit_shutdown(bot=bot)
    await bot.session.close()
```

<!-- invisible-code-block: python
await test_report()
-->

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Lifecycle](../providers/lifecycle.md): finalizers and container teardown.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(dispatcher, container, *, auto_inject=False)` | Stores the container on the dispatcher, registers `aiogram_update_provider`/`aiogram_event_provider`, wires `dispatcher.startup`/`dispatcher.shutdown` to open/close the container, and installs the per-update middleware. With `auto_inject=True`, also wraps every handler already registered on the dispatcher at startup. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-update child container. |
| `inject` | Decorator for an aiogram handler; resolves its `FromDI`-annotated parameters. Not needed when `setup_di(..., auto_inject=True)` is used. Raises `RuntimeError` naming `setup_di` when an update reaches it without the middleware installed. |
| `fetch_di_container(dispatcher)` | Returns the root `Container` stored on the dispatcher. |
| `aiogram_update_provider` | `ContextProvider` for the current `aiogram.types.Update` (REQUEST scope). |
| `aiogram_event_provider` | `ContextProvider` for the current `aiogram.types.TelegramObject` (REQUEST scope), the concrete event unwrapped from the `Update`. |
