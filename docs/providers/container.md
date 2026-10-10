# Container

The container provider is a special provider that you should not initialize.
It is automatically registered with each container, so you can resolve the container itself directly.

## Injecting the container itself

You can inject the container into your dependencies in two ways:

### Automatic injection (type-based)

If your creator function has a parameter annotated with `Container`, it will be automatically resolved:

```python
from modern_di import Container, Group, Scope, providers

def my_creator(di_container: Container) -> str:
    # Access the container's scope or other properties
    return f"Container scope: {di_container.scope.name}"

class Dependencies(Group):
    my_factory = providers.Factory(my_creator, scope=Scope.APP)

container = Container(groups=[Dependencies])
result = container.resolve(str)
# result: "Container scope: APP"
```

### Explicit injection

You can also explicitly inject the container using `providers.container_provider`. Reach for this when the parameter is not annotated as `Container` (so type-based injection can't find it), or when you want an explicit binding instead of relying on the type:

```python
import typing

from modern_di import Container, Group, Scope, providers

def another_creator(di_container: typing.Any) -> str:
    return f"resolved from {di_container.scope.name} scope"

class Dependencies(Group):
    another_factory = providers.Factory(
        another_creator,
        scope=Scope.APP,
        kwargs={"di_container": providers.container_provider}
    )

container = Container(groups=[Dependencies])
result = container.resolve(str)
# result: "resolved from APP scope"
```

## Which container you get

Resolving `Container` returns the **calling container**: the deepest, most-specific container in
the active chain, not the `APP` root. The `container_provider` hands back whichever container
ran the resolve, so a `REQUEST` child resolves `Container` to *itself*:

```python
app_container = Container(scope=Scope.APP)
request_container = app_container.build_child_container(scope=Scope.REQUEST)

assert app_container.resolve(Container) is app_container
assert request_container.resolve(Container) is request_container  # the child, not the APP root
```

The same holds for type-based injection: a creator with a `Container` parameter receives the
container that is resolving it. This means request-scoped code reaches the request container (and its
context/cache), while app-scoped code reaches the app container.

## Registering providers after construction

`container.add_providers(*providers)` registers additional providers on a **root** container after
it's built. Framework integrations use it to register their connection providers. Raises
`ChildContainerRegistrationError` if called on a child container. See [Writing an integration](../integrations/writing-integrations.md#the-contract) for
the full contract.

## Looking up a provider

`container.find_provider(SomeType)` returns the provider registered for `SomeType`, or `None` when
nothing is. Every container in a tree sees the same providers, so a child answers the same as its
root. The lookup ignores overrides and the closed state, and it never resolves anything:

<!-- invisible-code-block: python
class UserRepository: ...


app_container.add_providers(providers.Factory(UserRepository, scope=Scope.REQUEST))
-->

```python
provider = request_container.find_provider(UserRepository)
if provider is not None:
    repository = request_container.resolve_provider(provider)
```

## Resolving a provider or type

`container.resolve_dependency(dep)` accepts either a provider reference or a type and dispatches to
`resolve_provider` or `resolve` accordingly. It is the single entry point integrations use to
resolve a `FromDI`-style marker. See [Writing an integration](../integrations/writing-integrations.md#the-contract).

## See also

- [Context providers](context.md#context-propagation) covers how context values reach (and don't
  reach) a `ContextProvider`.
- [Advanced / low-level API](advanced-api.md) lists the public modules and documents
  `find_container`, `parent_container` and `Group.get_providers()`.
