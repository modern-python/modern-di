# Pydantic AI agents

Pydantic AI already has a seam for dependencies: an agent declares a `deps_type`, each run receives
`deps`, and every tool reads them from `RunContext.deps`. Pass a `modern-di` container as `deps`, and
tools resolve what they need from it. No integration package is needed.

## One container per run

Open a `Scope.REQUEST` child for each run and pass it as `deps`. Tools resolve from `ctx.deps`, so
everything they get is scoped to that run, and the child's finalizers run when the `async with` block
exits.

<!-- invisible-code-block: python
import os

os.environ.setdefault("OPENAI_API_KEY", "placeholder")
-->

```python
import dataclasses

from modern_di import Container, Group, Scope, providers
from pydantic_ai import Agent, RunContext


@dataclasses.dataclass
class Settings:
    greeting: str = "Hello"


@dataclasses.dataclass
class UserRepository:
    settings: Settings

    def name(self, user_id: int) -> str:
        return f"user-{user_id}"


class Dependencies(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    users = providers.Factory(UserRepository, scope=Scope.REQUEST)


container = Container(groups=[Dependencies])
agent = Agent("openai:gpt-5", deps_type=Container)


@agent.tool
def greet(ctx: RunContext[Container], user_id: int) -> str:
    users = ctx.deps.resolve(UserRepository)
    settings = ctx.deps.resolve(Settings)
    return f"{settings.greeting}, {users.name(user_id)}"


async def answer(prompt: str) -> str:
    async with container.build_child_container(scope=Scope.REQUEST) as request_container:
        result = await agent.run(prompt, deps=request_container)
    return result.output
```

<!-- invisible-code-block: python
from pydantic_ai.models.test import TestModel

async with container:
    with agent.override(model=TestModel()):
        assert "Hello, user-" in await answer("greet a user")
-->

Open the root container once at startup with `async with container:`, as in any other application.
`agent.run_sync(...)` works the same way inside a `with` block, and so do `agent.run_stream(...)` and
`agent.iter(...)`, as long as the child stays open until the run finishes.

If the agent also needs your own deps object, register it with the container instead: declare a
provider for it and resolve it in the tool.

## One container per tool call

Pydantic AI runs the tool calls from one model response concurrently. They all resolve from the same
run container, so a cached `Scope.REQUEST` instance is shared between them. That is wrong for objects
that must not be used concurrently, such as an `AsyncSession`. Give each tool call its own
`Scope.ACTION` child with a small capability:

```python
import contextvars
import typing

from modern_di import Container, Scope
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

action_container: contextvars.ContextVar[Container] = contextvars.ContextVar("action_container")


class ActionScope(AbstractCapability[Container]):
    """Open a Scope.ACTION child of the run's container for each tool call."""

    async def wrap_tool_execute(
        self,
        ctx: RunContext[Container],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: typing.Any,
        handler: typing.Any,
    ) -> typing.Any:
        async with ctx.deps.build_child_container(scope=Scope.ACTION) as child:
            token = action_container.set(child)
            try:
                return await handler(args)
            finally:
                action_container.reset(token)


agent = Agent("openai:gpt-5", deps_type=Container, capabilities=[ActionScope()])


@agent.tool_plain
async def save_note(note: str) -> str:
    session = action_container.get().resolve(Session)
    ...
```

<!-- invisible-code-block: python
from modern_di import Group, providers
from pydantic_ai.models.test import TestModel


class Session: ...


class NoteDependencies(Group):
    session = providers.Factory(Session, scope=Scope.ACTION)


with agent.override(model=TestModel()):
    async with Container(groups=[NoteDependencies]).build_child_container(scope=Scope.REQUEST) as run_container:
        await agent.run("save a note", deps=run_container)
-->

Declare per-call providers at `Scope.ACTION`, for example
`providers.Factory(Session, scope=Scope.ACTION, cache=providers.CacheSettings(finalizer=...))`. Each
tool call gets its own instance, and its finalizer runs when that call returns. The container lives in
a `ContextVar` rather than on the capability, because one capability instance serves all the
concurrent calls; each call sees only the child it opened.

## See also

- [Scopes](../providers/scopes.md), for where `Scope.ACTION` sits in the ladder.
- [Lifecycle](../providers/lifecycle.md), for finalizers and close order.
