# Container Provider

The Container Provider is a special provider that you should not initialize.
It is automatically registered with each container, so you can resolve the container itself directly.

## Injecting the Container Itself

You can inject the container into your dependencies in two ways:

### Automatic Injection (Type-Based)

If your creator function has a parameter annotated with `Container`, it will be automatically resolved:

```python
from modern_di import Container, Group, Scope, providers

def my_creator(di_container: Container) -> str:
    # Access the container's scope or other properties
    return f"Container scope: {di_container.scope.name}"

class Dependencies(Group):
    my_factory = providers.Factory(scope=Scope.APP, creator=my_creator)

container = Container(groups=[Dependencies])
result = container.resolve(str)
# result: "Container scope: APP"
```

### Explicit Injection

You can also explicitly inject the container using `providers.container_provider`:

```python
from modern_di import Container, Group, Scope, providers

def another_creator(di_container: Container) -> str:
    # Use the container to manually resolve dependencies
    return "some value"

class Dependencies(Group):
    another_factory = providers.Factory(
        scope=Scope.APP,
        creator=another_creator,
        kwargs={"di_container": providers.container_provider}
    )
```

## Context Propagation

`ContextRegistry` is **per-container**. Calling `set_context` on a parent container does not propagate to child containers that were already built — each container keeps its own context map.

!!! warning "set_context only affects this container"
    The following does **not** work as written:

    ```python
    app_container = Container()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    app_container.set_context(MyContext, value)  # invisible to request_container
    ```

    Either set context **before** building the child, or pass it via `build_child_container`:

    ```python
    # Option A: set on the parent first
    app_container = Container()
    app_container.set_context(MyContext, value)
    request_container = app_container.build_child_container(scope=Scope.REQUEST)

    # Option B: pass context directly to the child
    request_container = app_container.build_child_container(
        scope=Scope.REQUEST, context={MyContext: value}
    )
    ```
