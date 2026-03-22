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
    return f"Container scope: {di_container.scope}"

class Dependencies(Group):
    my_factory = providers.Factory(scope=Scope.APP, creator=my_creator)

container = Container(groups=[Dependencies])
result = container.resolve(str)
# result: "Container scope: Scope.APP"
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
