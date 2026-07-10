# Usage with `Celery`

## How to use

### 1. Install `modern-di-celery`

=== "uv"

      ```bash
      uv add modern-di-celery
      ```

=== "pip"

      ```bash
      pip install modern-di-celery
      ```

=== "poetry"

      ```bash
      poetry add modern-di-celery
      ```

### 2. Apply to your application

```python
import dataclasses
import typing

from celery import Celery
from modern_di import Container, Group, Scope, providers
from modern_di_celery import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    greeting: str = "hello"


@dataclasses.dataclass(kw_only=True, slots=True)
class Greeter:
    settings: Settings        # auto-injected by type

    def greet(self, name: str) -> str:
        return f"{self.settings.greeting}, {name}"


class AppGroup(Group):
    settings = providers.Factory(
        Settings,
        scope=Scope.APP,
        cache=True,
    )
    greeter = providers.Factory(
        Greeter,
        scope=Scope.REQUEST,
    )


app = Celery("myapp", broker="redis://localhost")
setup_di(app, Container(groups=[AppGroup], validate=True))


@app.task
@inject
def greet(
    name: str,
    greeter: typing.Annotated[
        Greeter,
        FromDI(Greeter),    # resolve by type
    ],
) -> str:
    return greeter.greet(name)
```

`setup_di(app, container)` stores the container on `app.conf` and registers `worker_process_init`/`worker_process_shutdown` signal handlers that open/close it — those fire when a real `celery worker` process starts and stops, so a script or test that calls tasks without spinning one up (e.g. with `task_always_eager = True`) must drive the container lifecycle itself; see [Worker-process lifecycle](#worker-process-lifecycle) below.

`@inject` builds a `Scope.REQUEST` child container per call and resolves `FromDI`-annotated parameters from it — it looks the container up through Celery's `current_app` proxy at call time, not the `app` object captured at decoration time, so it always resolves against whichever app is currently active.

## Scopes

The integration creates a `Scope.REQUEST` child container **for each task invocation**, whether wired via `@inject` or [`DITask`](#the-ditask-base-class). REQUEST-scoped providers (and their finalizers) live for the duration of that one call; the child container is closed with `close_sync()` once the task returns, including when it raises. APP-scoped providers persist for the whole worker process — `setup_di` opens the APP container on `worker_process_init` and closes it with `close_sync()` on `worker_process_shutdown`.

There is no `Scope.SESSION` for Celery — a task queue doesn't have a session concept comparable to websockets.

## Sync resolution, no connection object

`FromDI` resolves its dependency with `Container.resolve_dependency(...)`, which is synchronous — modern-di's resolution is always sync, regardless of the framework. Celery tasks are themselves sync callables, so the per-task `Scope.REQUEST` container is torn down the same way it's built: `@inject` calls `close_sync()` in a `finally` block after the task returns. There is no async counterpart — REQUEST-scoped finalizers must be sync (or `close_sync`-compatible) for Celery tasks.

Unlike aiohttp, FastAPI, or taskiq, a Celery task has no framework request or message object comparable to an HTTP request or a broker message — `modern_di_celery` does not register a context provider, and there is no implicit/explicit "framework context object" for this integration. Pass whatever per-call data a task needs through its own arguments (or `self.request` on a bound task, which is Celery's own mechanism, unrelated to modern-di).

## The `DITask` base class

`DITask` applies `@inject` to a task's `run` method automatically, so individual tasks don't need their own `@inject` decorator. Apply it to every task on an app with `task_cls=DITask`:

```python
import typing

from celery import Celery
from modern_di import Container, Group, Scope, providers
from modern_di_celery import DITask, FromDI, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)


app = Celery("myapp", broker="redis://localhost", task_cls=DITask)
setup_di(app, Container(groups=[AppGroup], validate=True))


@app.task
def greet(name: str, settings: typing.Annotated[Settings, FromDI(Settings)]) -> str:
    return f"{settings.greeting}, {name}"
```

Or apply it to a single task instead of the whole app:

```python
import typing

from celery import Celery
from modern_di import Container, Group, Scope, providers
from modern_di_celery import DITask, FromDI, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)


app = Celery("myapp", broker="redis://localhost")
setup_di(app, Container(groups=[AppGroup], validate=True))


@app.task(base=DITask)
def greet(name: str, settings: typing.Annotated[Settings, FromDI(Settings)]) -> str:
    return f"{settings.greeting}, {name}"
```

`DITask.__init__` wraps `self.run` with `inject` the first time the task class is instantiated (Celery instantiates each task class once per app) and resets `self.__header__` via `head_from_fun` so Celery still binds call arguments against the *visible*, non-DI signature. It skips re-wrapping if `run` is already injected, so stacking an explicit `@inject` under `@app.task(base=DITask)` is safe and only wraps once.

## Worker-process lifecycle

`setup_di` connects to Celery's `worker_process_init` and `worker_process_shutdown` signals with `weak=False` — Celery signals default to weak references, which would otherwise let the handlers be garbage-collected before a worker process ever fires them. Both signals fire once per **worker process**, not per task: `container.open()` runs on `worker_process_init`, `container.close_sync()` runs on `worker_process_shutdown`. APP-scoped providers are therefore built once per worker process and torn down when it exits.

A real `celery worker` invocation fires both signals automatically. Code that calls tasks without a running worker — a script, or a test using `task_always_eager` — must trigger the same signals (or drive the container directly) itself:

```python
from celery import Celery, signals
from modern_di import Container, Group, Scope, providers
from modern_di_celery import setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)


app = Celery("myapp", broker="memory://", backend="cache+memory://")
app.conf.task_always_eager = True
app.conf.task_store_eager_result = True
setup_di(app, Container(groups=[AppGroup], validate=True))


@app.task
def ping() -> str:
    return "pong"


signals.worker_process_init.send(sender=None)    # a real worker fires this on startup
print(ping.delay().get())    # -> "pong"
signals.worker_process_shutdown.send(sender=None)    # a real worker fires this on shutdown
```

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Wire the APP-scope container into Celery — stores it on `app.conf` and opens/closes it on `worker_process_init`/`worker_process_shutdown`. Returns the container. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a plain type. |
| `@inject` | Decorator that builds a `Scope.REQUEST` child container per call, resolves `FromDI`-annotated parameters from it, and closes the child container with `close_sync()` afterwards. |
| `DITask` | `Task` subclass that applies `@inject` to a task's `run` method automatically; pass `task_cls=DITask` to `Celery(...)` or `base=DITask` to `@app.task(...)`. |
| `fetch_di_container(app)` | Returns the APP-scope container registered with the Celery app. |
