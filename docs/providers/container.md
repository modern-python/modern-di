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

container = Container(groups=[Dependencies], validate=True)
result = container.resolve(str)
# result: "Container scope: APP"
```

### Explicit Injection

You can also explicitly inject the container using `providers.container_provider`. Reach for this when the parameter is **not** annotated as `Container` (so type-based injection can't find it), or when you want an explicit binding instead of relying on the type:

```python
from modern_di import Container, Group, Scope, providers

def another_creator(di_container: Container) -> str:
    # The injected container is real — use it
    return f"resolved from {di_container.scope.name} scope"

class Dependencies(Group):
    another_factory = providers.Factory(
        scope=Scope.APP,
        creator=another_creator,
        kwargs={"di_container": providers.container_provider}
    )

container = Container(groups=[Dependencies], validate=True)
result = container.resolve(str)
# result: "resolved from APP scope"
```

## Which container you get

Resolving `Container` returns the **calling container** — the deepest, most-specific container in
the active chain, not the `APP` root. The `container_provider` simply hands back whichever container
ran the resolve, so a `REQUEST` child resolves `Container` to *itself*:

```python
app_container = Container(scope=Scope.APP, validate=True)
request_container = app_container.build_child_container(scope=Scope.REQUEST)

assert app_container.resolve(Container) is app_container
assert request_container.resolve(Container) is request_container  # the child, not the APP root
```

The same holds for type-based injection: a creator with a `Container` parameter receives the
container that is resolving it. This means request-scoped code reaches the request container (and its
context/cache), while app-scoped code reaches the app container.

## See also

- **Context propagation** — how context values reach (and don't reach) a `ContextProvider` is
  covered on the [Context Providers](context.md#context-propagation) page.
- **Low-level API** — `find_container`, `scope_map`, `Group.get_providers()`, and subclassing
  `AbstractProvider` are documented under [Advanced / low-level API](advanced-api.md).
