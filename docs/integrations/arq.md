# Usage with `arq`

## How to use

### 1. Install `modern-di-arq`

=== "uv"

      ```bash
      uv add modern-di-arq
      ```

=== "pip"

      ```bash
      pip install modern-di-arq
      ```

=== "poetry"

      ```bash
      poetry add modern-di-arq
      ```

### 2. Apply to your application

```python
import typing

from arq.connections import RedisSettings
from modern_di import Container, Group, Scope, providers
from modern_di_arq import FromDI, inject, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class Greeter:
    def __init__(self, settings: Settings) -> None:   # auto-injected by type
        self._settings = settings

    def greet(self, name: str) -> str:
        return f"{self._settings.greeting}, {name}"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    greeter = providers.Factory(Greeter, scope=Scope.REQUEST)


@inject
async def greet(
    ctx: dict[str, typing.Any],       # arq passes its context dict as the first argument
    name: str,
    greeter: typing.Annotated[Greeter, FromDI(Greeter)],   # resolve by type
) -> str:
    return greeter.greet(name)


class WorkerSettings:
    functions = [greet]
    redis_settings = RedisSettings(host="localhost")


setup_di(WorkerSettings, Container(groups=[AppGroup], validate=True))
```

Run the worker as usual — `arq mymodule.WorkerSettings` — and enqueue jobs from
anywhere:

```python
from arq import create_pool
from arq.connections import RedisSettings


async def main() -> None:
    pool = await create_pool(RedisSettings(host="localhost"))
    await pool.enqueue_job("greet", "world")    # pass only real args; DI params are resolved for you
```

`setup_di(worker_settings, container)` seeds the container into arq's `ctx` dict
(arq's per-worker state store) and wraps four of arq's lifecycle hooks:
`on_startup`/`on_shutdown` open and close the root container, and
`on_job_start`/`on_job_end` build and close a `Scope.REQUEST` child container
around each job. Any hook you already defined still runs — yours runs *after*
ours on startup/job-start and *before* ours on shutdown/job-end, so your code
always sees a live container. It accepts a `WorkerSettings` class (the common
case) or a plain settings `dict`, and returns the container.

`@inject` resolves each `FromDI`-annotated parameter from the per-job child
container and forwards it to your task. Your task **must** declare arq's `ctx`
dict as its first parameter (arq calls every task as `task(ctx, *args)`).
Injection is parameter-order-insensitive — a `FromDI` parameter may sit anywhere
in the signature — and a task with no `FromDI` parameter is returned unchanged.

## Scopes

The integration builds one `Scope.REQUEST` child container **per job**. It is
created in `on_job_start` and closed with `close_async()` in `on_job_end`, which
arq runs whether the job succeeded or raised — so REQUEST-scoped providers (and
their finalizers) live exactly for the duration of one job and never leak on the
error path. APP-scoped providers persist for the whole worker: `setup_di` opens
the root container on `on_startup` and closes it on `on_shutdown`, running
APP-scoped finalizers once when the worker stops.

There is no `Scope.SESSION` for arq — a job queue has no session concept
comparable to a websocket connection.

## Async resolution, no connection object

`FromDI` resolves its dependency with `Container.resolve_dependency(...)`, which
is synchronous — modern-di's resolution is always sync, regardless of the
framework. Container *lifecycle* here is async, matching arq: the root and each
per-job child are closed with `close_async()`, so REQUEST- and APP-scoped
finalizers may be async (or sync).

arq's per-job `ctx` is a plain `dict` (`job_id`, `job_try`, `redis`, ...), not a
dedicated request/message type, so — like Celery and Typer — `modern_di_arq`
registers no context provider. A task that needs job metadata reads it from the
`ctx` argument arq already passes. If you need the root container elsewhere (for
example in your own `on_job_start`), `fetch_di_container(ctx)` returns it.

## Restart safety

`setup_di` wires `container.open()` onto `on_startup`, and `open()` is a no-op on
an already-open container. A worker that starts, stops (closing the container),
and starts again — a restart, or a test that runs the worker twice — reopens the
same container cleanly instead of raising. Calling `setup_di` twice on the same
`worker_settings` is rejected with a `TypeError`, since stacking the hook
wrappers would leak a per-job child container.

## Tasks with `*args`/`**kwargs`

`@inject` resolves dependencies by binding the task signature by name, which is
what makes injection order-insensitive. A task that mixes a `FromDI` parameter
with `*args` or `**kwargs` cannot be bound unambiguously, so `@inject` raises a
`TypeError` **at decoration time** rather than silently misrouting arguments.
Give an `@inject` task explicit named parameters. (A task with no `FromDI`
parameter is untouched and may use `*args`/`**kwargs` freely.)

## API

| Symbol | Description |
|---|---|
| `setup_di(worker_settings, container)` | Seed the root container into arq's `ctx` and wire root + per-job lifecycle onto arq's `on_startup`/`on_shutdown`/`on_job_start`/`on_job_end` hooks. Accepts a `WorkerSettings` class/object or a settings `dict`; composes with existing hooks; returns the container. Raises `TypeError` if called twice on the same `worker_settings`. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a plain type. |
| `@inject` | Decorator that resolves `FromDI`-annotated parameters from the per-job `Scope.REQUEST` child container. Order-insensitive; passthrough for tasks with no `FromDI`; raises `TypeError` at decoration if the task also declares `*args`/`**kwargs`. |
| `fetch_di_container(ctx)` | Returns the root container from an arq `ctx` dict. |
