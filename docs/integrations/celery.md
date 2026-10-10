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
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings   # APP-scoped, injected by type

    def render(self) -> str:
        return f"service={self.settings.service_name}"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


app = Celery("myapp", broker="redis://localhost")
container = Container(groups=[AppGroup])
setup_di(app, container)
container.validate()  # fails fast on a broken graph before the worker runs


@app.task
@inject
def run_report(report: typing.Annotated[Report, FromDI(Report)]) -> str:
    return report.render()
```

`setup_di(app, container)` stores the container on `app.conf` and connects Celery's
worker signals that open and close it. `@inject` builds a `Scope.REQUEST` child container
for each task call and resolves `FromDI`-annotated parameters from it. It looks the
container up through Celery's `current_app` at call time, so it resolves against
whichever app is active.

Celery closes containers with `close_sync()`, both the per-task child and the root at
worker shutdown. Finalizers must therefore be sync: an async finalizer makes the close
raise `FinalizerError`.

## Scopes

The integration creates a `Scope.REQUEST` child container for each task call, whether
the task is wired with `@inject` or with [`DITask`](#the-ditask-base-class).
REQUEST-scoped providers and their finalizers live for that one call. The child is
closed with `close_sync()` once the task returns or raises. An async finalizer on a
REQUEST-scoped provider makes the task itself fail with `FinalizerError`.

Resolution is synchronous, as everywhere in modern-di, and Celery tasks are sync
callables, so there is no async teardown path.

There is no `Scope.SESSION` for Celery: a task queue has no session concept
comparable to websockets.

## Root container lifecycle

A constructed container is already open, so tasks resolve without any worker signal
having fired. The signals matter for closing: `setup_di` closes the root with
`close_sync()` when the worker stops, which runs APP-scoped finalizers. Which signal
does the work depends on the pool:

| Pool | Opens the root on | Closes the root on |
|---|---|---|
| `prefork` | `worker_process_init`, in each child process | `worker_process_shutdown`, in each child process |
| `solo` | `worker_process_init` | `worker_shutdown` |
| `threads`, `gevent`, `eventlet` | `worker_init` | `worker_shutdown` |

Under prefork each child process gets its own APP-scoped instances. `worker_init` and
`worker_shutdown` fire in the main worker process under every pool; opening an open
container and closing one with nothing cached are both no-ops, so the overlap is
harmless.

!!! warning "The prefork pool fails on macOS"
    On macOS, billiard starts prefork children with the spawn method, which pickles
    the Celery app. The container that `setup_di` stores on `app.conf` cannot be
    pickled, so the worker stops at startup with
    `TypeError: cannot pickle '_thread._local' object`. Run the worker with
    `--pool=solo` or `--pool=threads` there.

Code that calls tasks without a worker, such as a script or a test in eager mode,
fires none of these signals. Close the root yourself when it is done, for example
with `with container:`, as in [Testing](#testing).

## Framework context objects

A Celery task has no framework request or message object, so `modern_di_celery`
registers no context provider. Pass the per-call data a task needs through its
arguments, or read `self.request` on a bound task.

## The `DITask` base class

`DITask` applies `@inject` to a task's `run` method, so individual tasks don't need
the decorator. Pass `task_cls=DITask` to apply it to every task on the app:

<!-- invisible-code-block: python
report_app, report_container, report_task = app, container, run_report
-->

```python
from modern_di_celery import DITask

app = Celery("myapp", broker="redis://localhost", task_cls=DITask)
container = Container(groups=[AppGroup])
setup_di(app, container)


@app.task
def labelled_report(label: str, report: typing.Annotated[Report, FromDI(Report)]) -> str:
    return f"{label}: {report.render()}"
```

To apply it to a single task instead, pass `base=DITask` to that task's decorator:
`@app.task(base=DITask)`. Celery still checks call arguments against the signature
without the `FromDI` parameters, so `labelled_report.delay()` with no `label` raises
`TypeError`. A task that also carries an explicit `@inject` is wrapped only once.

## Testing

With `task_always_eager`, a task runs in the calling process, so no worker signal
fires. Wrap the calls in `with container:` to close the root and run APP-scoped
finalizers at the end:

<!-- invisible-code-block: python
app, container, run_report = report_app, report_container, report_task
-->

```python
app.conf.task_always_eager = True

with container:
    assert run_report.delay().get() == "service=catalog"
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Multi-Group organization](../recipes/multi-group.md): structuring a larger container.
- [Lifecycle](../providers/lifecycle.md): finalizers and container teardown.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Wire the APP-scope container into Celery: stores it on `app.conf` and opens/closes it on `worker_process_init`/`worker_process_shutdown` and `worker_init`/`worker_shutdown`. Returns the container. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a plain type. |
| `@inject` | Decorator that builds a `Scope.REQUEST` child container per call, resolves `FromDI`-annotated parameters from it, and closes the child container with `close_sync()` afterwards. Raises `RuntimeError` naming `setup_di` when a task reaches it without `setup_di` called. A task with `FromDI` parameters that also declares `*args`/`**kwargs` raises `TypeError` at decoration. |
| `DITask` | `Task` subclass that applies `@inject` to a task's `run` method automatically; pass `task_cls=DITask` to `Celery(...)` or `base=DITask` to `@app.task(...)`. |
| `fetch_di_container(app)` | Returns the APP-scope container registered with the Celery app. Raises `RuntimeError` naming `setup_di` when called on an app without `setup_di` called. |
