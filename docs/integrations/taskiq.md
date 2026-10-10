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
from taskiq import InMemoryBroker


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


broker = InMemoryBroker()
container = Container(groups=[AppGroup])
setup_di(broker, container)
container.validate()  # after setup_di: its context provider is now registered


@broker.task
async def get_report(
    report: typing.Annotated[Report, FromDI(Report)],
) -> dict[str, str]:
    return report.as_dict()
```

`setup_di(broker, container)` stores the container on `broker.state`, registers the
message context provider, and hooks the root container's lifecycle to taskiq's worker
events. Each task that uses `FromDI` gets its own `Scope.REQUEST` child container.

## Scopes

The integration creates a `Scope.REQUEST` child container for each task that uses `FromDI`,
built through `TaskiqDepends` when the task's dependencies are resolved. A task with no
`FromDI` parameter gets no child container. REQUEST-scoped providers and their finalizers
live for that one task, and the child is closed after the task returns or raises.

Resolution is synchronous, as everywhere in modern-di, while the child is closed with
`close_async()`, so REQUEST-scoped finalizers may be async or sync.

There is no `Scope.SESSION` for taskiq: a task queue doesn't have a session concept
comparable to websockets.

## Root container lifecycle

`setup_di` opens the root container on `TaskiqEvents.WORKER_STARTUP` and closes it with
`close_async()` on `WORKER_SHUTDOWN`, which runs APP-scoped finalizers. `taskiq worker`
fires both. With an `InMemoryBroker`, `async with broker:` fires both too.

!!! warning "`run_receiver_task` never closes the root"
    A receiver embedded with `taskiq.api.run_receiver_task(...)` never calls
    `broker.shutdown()`, so `WORKER_SHUTDOWN` never fires and APP-scoped finalizers
    never run, whatever `run_startup` is set to. Tasks still resolve, since a
    constructed container is already open. After the receiver stops, call
    `await broker.shutdown()` or `await container.close_async()` yourself.

## Framework context objects

`taskiq.TaskiqMessage` is automatically made available by the integration, so factories can declare it as a parameter and get the message that triggered the current task. See [Framework context objects](../providers/context.md#framework-context-objects) for how implicit and explicit resolution work.

The following context provider is also available for explicit import:

- `taskiq_message_provider` provides the current `taskiq.TaskiqMessage` object.

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

## Testing

Enter an `InMemoryBroker` with `async with` so the worker events fire, then send a task and
wait for its result:

```python
async with broker:
    task = await get_report.kiq()
    result = await task.wait_result()
assert result.return_value == {"service": "catalog"}
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Async resources via lifespan](../recipes/async-lifespan.md): constructing async resources with finalizers.
- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(broker, container)` | Wire the APP-scope container into taskiq: a REQUEST child container is then built through `TaskiqDepends` for each task that uses `FromDI`; opens/closes the APP container on worker startup/shutdown. |
| `FromDI(provider_or_type, *, use_cache=True)` | Marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a plain type. `use_cache` is passed through to `TaskiqDepends`. Raises `RuntimeError` naming `setup_di` when a task reaches it without `setup_di` called. |
| `fetch_di_container(broker)` | Returns the APP-scope container registered with the taskiq broker. |
| `taskiq_message_provider` | `ContextProvider` for the current `taskiq.TaskiqMessage`. |
