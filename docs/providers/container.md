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

Context never propagates between containers. A `ContextProvider` reads the context registry of the container **at the provider's own scope** — build order is irrelevant.

!!! warning "Scope determines which container is read, not timing"
    Setting context on a parent container never reaches a child-scoped provider, regardless of when you call `set_context`:

    ```python
    # ❌ Broken: MyContext provider has scope=Scope.REQUEST, so it reads the REQUEST
    # container's registry. Setting it on the APP parent has no effect.
    app_container = Container()
    app_container.set_context(MyContext, value)  # ignored for REQUEST-scoped providers
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    ```

    For a REQUEST-scoped `ContextProvider`, set the value on the request container:

    ```python
    # Option A: pass context directly when building the child
    request_container = app_container.build_child_container(
        scope=Scope.REQUEST, context={MyContext: value}
    )

    # Option B: set on the request container after building it
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.set_context(MyContext, value)
    ```

    Setting context on the parent only works when the `ContextProvider`'s scope matches the parent's scope.
