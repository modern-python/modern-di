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
import dataclasses
import typing

from arq.connections import RedisSettings
from modern_di import Container, Group, Scope, providers
from modern_di_arq import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings   # APP-scoped, injected by type

    def render(self) -> str:
        return f"service={self.settings.service_name}"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


@inject
async def run_report(
    ctx: dict[str, typing.Any],      # arq passes its context dict as the first argument
    report: typing.Annotated[Report, FromDI(Report)],
) -> str:
    return report.render()


class WorkerSettings:
    functions = [run_report]
    redis_settings = RedisSettings(host="localhost")


container = Container(groups=[AppGroup])
setup_di(WorkerSettings, container)
container.validate()  # fails fast on a broken graph before the worker runs
```

Run the worker as usual (`arq mymodule.WorkerSettings`) and enqueue jobs from
anywhere:

```python
from arq import create_pool
from arq.connections import RedisSettings


async def main() -> None:
    pool = await create_pool(RedisSettings(host="localhost"))
    await pool.enqueue_job("run_report")
```

`setup_di(worker_settings, container)` puts the container in arq's `ctx` dict and
wraps four of arq's hooks: `on_startup` and `on_shutdown` open and close the root
container, and `on_job_start` and `on_job_end` build and close a `Scope.REQUEST`
child around each job. It accepts a `WorkerSettings` class or a plain settings
`dict`, and returns the container.

`@inject` resolves each `FromDI`-annotated parameter from the job's child container
and passes it to your task. arq calls every task as `task(ctx, *args)`, so `ctx`
must be the first parameter apart from the `FromDI` ones, which may sit anywhere in
the signature. A task with no `FromDI` parameter is returned unchanged.

## Scopes

`on_job_start` builds one `Scope.REQUEST` child container per job. For an `@inject`
task, the wrapper closes it when the task body exits, whether it returned or
raised. Nested or concurrent `@inject` calls in the same job share the child, and
the last one to exit closes it. `on_job_end` closes the child only if it is still
open, which covers a job that ran no `@inject` wrapper.

Resolution is synchronous, as everywhere in modern-di. The child is closed with
`close_async()`, so REQUEST-scoped finalizers may be async or sync.

There is no `Scope.SESSION` for arq: a job queue has no session concept
comparable to a websocket connection.

## Root container lifecycle

`on_startup` opens the root container and `on_shutdown` closes it with
`close_async()`, which runs APP-scoped finalizers once when the worker stops. A
worker that starts again on the same container, after a restart or in a test that
runs the worker twice, reopens it on startup.

A hook you already defined on `WorkerSettings` still runs. Yours runs after ours
on startup and job start, and before ours on shutdown and job end. The root
container is open in all of them, but for an `@inject` task the job's child is
already closed by the time your `on_job_end` runs.

Calling `setup_di` twice on the same `worker_settings` raises a `TypeError`,
because stacking the hook wrappers would leak a per-job child container.

## Framework context objects

arq's per-job `ctx` is a plain `dict` (`job_id`, `job_try`, `redis` and so on),
so `modern_di_arq` registers no context provider. A task that needs job metadata
reads it from the `ctx` argument. To reach the root container elsewhere, for
example in your own `on_job_start`, call `fetch_di_container(ctx)`.

## Tasks with `*args`/`**kwargs`

`@inject` resolves dependencies by binding the task signature by name, which is
what makes injection order-insensitive. A task that mixes a `FromDI` parameter
with `*args` or `**kwargs` cannot be bound unambiguously, so `@inject` raises a
`TypeError` at decoration time. Give an `@inject` task explicit named parameters.
A task with no `FromDI` parameter is left untouched and may use `*args`/`**kwargs`
freely.

## Testing

A burst worker runs the queued jobs and stops, so it drives the whole lifecycle
in a test: startup, one child per job, and shutdown. It needs a running Redis.

<!-- skip: next "needs a running Redis server" -->

```python
from arq.worker import create_worker


async def test_run_report() -> None:
    pool = await create_pool(RedisSettings(host="localhost"))
    job = await pool.enqueue_job("run_report")
    worker = create_worker(WorkerSettings, burst=True, handle_signals=False)
    await worker.main()
    await worker.close()
    assert await job.result() == "service=catalog"
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Async resources via lifespan](../recipes/async-lifespan.md): constructing async resources with finalizers.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(worker_settings, container)` | Seed the root container into arq's `ctx` and wire root + per-job lifecycle onto arq's `on_startup`/`on_shutdown`/`on_job_start`/`on_job_end` hooks. Accepts a `WorkerSettings` class/object or a settings `dict`; composes with existing hooks; returns the container. Raises `TypeError` if called twice on the same `worker_settings`. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a plain type. |
| `@inject` | Decorator that resolves `FromDI`-annotated parameters from the per-job `Scope.REQUEST` child container. Order-insensitive; passthrough for tasks with no `FromDI`; raises `TypeError` at decoration if the task also declares `*args`/`**kwargs`; raises `RuntimeError` naming `setup_di` when a job reaches it without the modern-di hooks installed. |
| `fetch_di_container(ctx)` | Returns the root container from an arq `ctx` dict. |
