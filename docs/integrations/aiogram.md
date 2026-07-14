# Usage with `aiogram`

aiogram has no dependency-injection system of its own, so `modern-di-aiogram`
uses the `@inject` decorator with `FromDI` markers (or `auto_inject=True` to
skip the decorator entirely). `setup_di` opens the root container on
dispatcher startup, closes it on shutdown, and installs middleware that opens
a per-update child container automatically.

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
setup_di(dispatcher, Container(groups=[AppGroup], validate=True))


@dispatcher.message()
@inject
async def greet(
    message: Message,
    report: typing.Annotated[Report, FromDI(Report)],
) -> None:
    await message.answer(str(report.as_dict()))
```

`setup_di(dispatcher, container)` stores the container on the dispatcher,
registers `dispatcher.startup`/`dispatcher.shutdown` handlers that open/close
it, and installs an update-level outer middleware that builds a per-update
child container.

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
setup_di(dispatcher, Container(groups=[AppGroup], validate=True), auto_inject=True)
```

!!! warning "Register handlers before startup"
    `auto_inject` wraps handlers on `dispatcher.startup`, which fires from
    `dispatcher.emit_startup()` — the call `start_polling()`/`start_webhook()`
    makes before serving updates. Only handlers registered (via
    `dispatcher.include_router()` or the decorators directly) **before**
    `emit_startup()` runs are wrapped; a handler added afterward is invoked
    without injection and any `FromDI` parameter on it is left unresolved.

## Scopes

The integration creates one `Scope.REQUEST` child container **per update**.
The middleware is installed on `dispatcher.update` as an
[outer middleware](https://docs.aiogram.dev/en/latest/dispatcher/middlewares.html),
so it wraps every update regardless of which router or handler ultimately
processes it. The child container is closed after the handler runs —
including when it raises.

There is no `Scope.SESSION` for aiogram — each Telegram update is handled
independently; there's no persistent per-chat/per-user connection comparable
to a WebSocket. See [the scope hierarchy](../providers/scopes.md#the-scope-dependency-rule).

## Sync resolution, async cleanup

`FromDI` resolves its dependency with `Container.resolve_dependency(...)`,
which is synchronous — modern-di's resolution is always sync, regardless of
the framework. The per-update `Scope.REQUEST` child container that resolution
runs against is nevertheless torn down asynchronously: after the handler
finishes (or raises), the integration awaits `child_container.close_async()`.
So async finalizers on REQUEST-scoped providers run correctly, while the
factories themselves must build synchronously.

## Framework context objects

`aiogram.types.Update` and the concrete event it carries (`Message`,
`CallbackQuery`, etc.) are automatically made available by the integration,
so factories can declare them as parameters — see
[Framework Context Objects](../providers/context.md#framework-context-objects)
for how implicit and explicit resolution work.

The following context providers are also available for explicit import:

- `aiogram_update_provider` — provides the current `aiogram.types.Update`.
- `aiogram_event_provider` — provides the current `aiogram.types.TelegramObject`,
  the concrete event unwrapped from the `Update` (e.g. a `Message` or
  `CallbackQuery` instance).

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

`aiogram_event_provider` is bound to the base `TelegramObject` type, so
narrowing a parameter to a concrete event type (like `Message`) requires
wiring it explicitly with `FromDI`:

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

## See also

- [Testing with overrides](../recipes/testing-overrides.md) — swap providers in your tests.
- [Lifecycle](../providers/lifecycle.md) — finalizers and container teardown.
- [Scopes](../providers/scopes.md) — the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(dispatcher, container, *, auto_inject=False)` | Stores the container on the dispatcher, registers `aiogram_update_provider`/`aiogram_event_provider`, wires `dispatcher.startup`/`dispatcher.shutdown` to open/close the container, and installs the per-update middleware. With `auto_inject=True`, also wraps every handler already registered on the dispatcher at startup. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-update child container. |
| `inject` | Decorator for an aiogram handler; resolves its `FromDI`-annotated parameters. Not needed when `setup_di(..., auto_inject=True)` is used. |
| `fetch_di_container(dispatcher)` | Returns the root `Container` stored on the dispatcher. |
| `aiogram_update_provider` | `ContextProvider` for the current `aiogram.types.Update` (REQUEST scope). |
| `aiogram_event_provider` | `ContextProvider` for the current `aiogram.types.TelegramObject` (REQUEST scope) — the concrete event unwrapped from the `Update`. |

## Usage with `aiogram-dialog`

[aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) runs inside
aiogram's dispatch, so the per-update child container that `setup_di`'s
middleware already builds is reachable from dialog code. `modern_di_aiogram.dialog`
adds a dialog-aware `inject` for **getters** and **callbacks** (`on_click`,
`on_start`/`on_close`, `on_process_result`) — install it with the normal
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
requires the normal `setup_di(dispatcher, container)` — its middleware provides
the per-update container.

- `modern_di_aiogram.dialog` has **no runtime dependency** on `aiogram-dialog`;
  install `aiogram-dialog` yourself.
- The `FromDI` marker is the same one used for handlers — it is re-exported from
  `modern_di_aiogram.dialog` for convenience.
- An `@inject` getter must still declare `**kwargs` (aiogram-dialog always calls
  getters with the full `middleware_data`), and a `FromDI` getter parameter must
  not share a name with a `middleware_data` key (e.g. `bot`, `event`).
