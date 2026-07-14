# Usage with `taskiq`

## How to use

### 1. Install `modern-di-taskiq`

=== "uv"

      ```bash
      uv add modern-di-taskiq
      ```

=== "pip"

      ```bash
      pip install modern-di-taskiq
      ```

=== "poetry"

      ```bash
      poetry add modern-di-taskiq
      ```

### 2. Apply to your application

```python
import dataclasses
import typing

from modern_di import Container, Group, Scope, providers
from modern_di_taskiq import FromDI, setup_di
from taskiq import InMemoryBroker, TaskiqMessage


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class TaskReport:
    settings: Settings          # APP-scoped, injected by type
    message: TaskiqMessage      # per-task context object, injected by type

    def as_dict(self) -> dict[str, str]:
        return {
            "service": self.settings.service_name,
            "task": self.message.task_name,
        }


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    task_report = providers.Factory(TaskReport, scope=Scope.REQUEST)


broker = InMemoryBroker()
setup_di(broker, Container(groups=[AppGroup], validate=True))


@broker.task
async def report(
    task_report: typing.Annotated[TaskReport, FromDI(TaskReport)],
) -> dict[str, str]:
    return task_report.as_dict()
```

`setup_di(broker, container)` stores the container on `broker.state` and registers `TaskiqEvents.WORKER_STARTUP`/`WORKER_SHUTDOWN` handlers that open/close it — those fire when the broker's worker process starts and stops, so a script that just calls tasks directly (like `InMemoryBroker` in a test) must drive the container lifecycle itself, e.g. `async with broker: ...` or an explicit `container.open()` / `await container.close_async()`.

## Scopes

The integration creates a `Scope.REQUEST` child container **for each task** the worker executes. REQUEST-scoped providers (and their finalizers) live for the duration of that one task — the child container is closed after the task returns, including when it raises. APP-scoped providers persist for the whole worker process; `setup_di` opens the APP container on `WORKER_STARTUP` and runs `await container.close_async()` on `WORKER_SHUTDOWN`.

There is no `Scope.SESSION` for taskiq — a task queue doesn't have a session concept comparable to websockets.

## Sync resolution, async cleanup

`FromDI` resolves its dependency with `Container.resolve_dependency(...)`, which is synchronous — modern-di's resolution is always sync, regardless of the framework. The per-task `Scope.REQUEST` child container that resolution runs against is nevertheless torn down asynchronously: after the task handler finishes (or raises), the integration awaits `container.close_async()` on it. So async finalizers on REQUEST-scoped providers run correctly, while the factories themselves must build synchronously.

## Framework context objects

`taskiq.TaskiqMessage` is automatically made available by the integration, so factories can declare it as a parameter and get the message that triggered the current task — see [Framework Context Objects](../providers/context.md#framework-context-objects) for how implicit and explicit resolution work.

The following context provider is also available for explicit import:

- `taskiq_message_provider` — provides the current `taskiq.TaskiqMessage` object.

### Implicit (type-based) usage

```python
import taskiq
from modern_di import Group, Scope, providers


def create_task_info(message: taskiq.TaskiqMessage) -> dict[str, str]:
    return {
        "task_id": message.task_id,
        "task_name": message.task_name,
    }


class AppGroup(Group):
    # The message dependency is resolved by type annotation
    task_info = providers.Factory(
        create_task_info,
        scope=Scope.REQUEST,
    )
```

### Explicit (provider-based) usage

```python
import taskiq
import modern_di_taskiq
from modern_di import Group, Scope, providers


def create_task_info(message: taskiq.TaskiqMessage) -> dict[str, str]:
    return {"task_id": message.task_id}


class AppGroup(Group):
    task_info = providers.Factory(
        create_task_info,
        scope=Scope.REQUEST,
        kwargs={"message": modern_di_taskiq.taskiq_message_provider},
    )
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md) — swap providers in your tests.
- [Async resources via lifespan](../recipes/async-lifespan.md) — constructing async resources with finalizers.
- [Lifecycle](../providers/lifecycle.md) — finalizers and `close_async()`.
- [Scopes](../providers/scopes.md) — the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(broker, container)` | Wire the APP-scope container into taskiq — creates a REQUEST child container per task and opens/closes the APP container on worker startup/shutdown. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a plain type. |
| `fetch_di_container(broker)` | Returns the APP-scope container registered with the taskiq broker. |
| `taskiq_message_provider` | `ContextProvider` for the current `taskiq.TaskiqMessage`. |
