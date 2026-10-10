# Container

A `Container` resolves providers. You build one root container, usually at `Scope.APP`, and a child
for each shorter-lived scope such as a request. Every container in a tree shares the same providers
and overrides, and each one owns its own cache and context. See [Scopes](scopes.md) for the scope
model and [Resolving dependencies](../introduction/resolving.md) for how a resolve works.

## Building a container

`Container(scope=Scope.APP, *, context=None, groups=None)` builds a root container, open and ready
to resolve:

- `scope`: any `IntEnum` member; anything else raises `InvalidScopeTypeError`.
- `context`: values for the root's [context providers](context.md). The dict is copied, so later
  changes to it are not seen.
- `groups`: a list of `Group` classes whose providers it registers. Passing a group together with
  its subclass, or one group twice, registers the same providers twice and raises
  `DuplicateProviderTypeError`.

<!-- invisible-code-block: python
import copy
-->

```python
import dataclasses

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(frozen=True)
class Settings:
    debug: bool


class Dependencies(Group):
    settings = providers.ContextProvider(Settings)


app_container = Container(groups=[Dependencies], context={Settings: Settings(debug=True)})
assert app_container.resolve(Settings).debug
assert copy.copy(app_container) is app_container
assert copy.deepcopy(app_container) is app_container
```

Children come from `build_child_container()`. `copy.copy()` and `copy.deepcopy()` return the
container itself, because a copy would own a cache whose finalizers never run.

## Methods at a glance

| Member | What it does | Covered in |
|---|---|---|
| `build_child_container(scope=, context=)` | builds a child at a deeper scope | [Scopes](scopes.md#building-child-containers) |
| `set_context(type, value)` | sets a context value on this container | [Context providers](context.md) |
| `resolve(type)`, `resolve_provider(provider)` | resolve by type or by provider | [Resolving dependencies](../introduction/resolving.md) |
| `resolve_dependency(dep)` | takes a provider or a type and calls `resolve_provider` or `resolve`; integrations use it for `FromDI`-style markers | [Writing an integration](../integrations/writing-integrations.md#the-contract) |
| `validate()` | checks the whole graph | [Lifecycle](lifecycle.md#validation) |
| `close_sync()`, `close_async()`, `with`, `async with` | run finalizers and close | [Lifecycle](lifecycle.md#closing-the-container) |
| `open()`, `closed` | reopen a closed container; whether it is closed | [Lifecycle](lifecycle.md#closing-and-reopening) |
| `override(provider, obj)`, `reset_override(provider)` | replace a provider's result, tree-wide | [Testing with overrides](../recipes/testing-overrides.md) |
| `add_providers(*providers)` | registers providers on a root | [below](#registering-providers-after-construction) |
| `find_provider(type)` | looks up the provider for a type | [below](#looking-up-a-provider) |
| `scope`, `parent_container`, `find_container(scope)` | navigate the container tree | [Advanced API](advanced-api.md#container-navigation) |

## Injecting the container itself

Every container registers `providers.container_provider` under the `Container` type, so a creator
parameter annotated `Container` receives a container:

```python
class JobRunner:
    def __init__(self, container: Container) -> None:
        self.container = container


class Jobs(Group):
    runner = providers.Factory(JobRunner, scope=Scope.REQUEST)


jobs_container = Container(groups=[Jobs])
request_container = jobs_container.build_child_container(scope=Scope.REQUEST)

assert request_container.resolve(JobRunner).container is request_container
```

For a parameter not annotated `Container`, wire `providers.container_provider` through `kwargs`:

```python
import typing


class Reporter:
    def __init__(self, di: typing.Any) -> None:
        self.di = di


class Reports(Group):
    reporter = providers.Factory(
        Reporter, scope=Scope.REQUEST, kwargs={"di": providers.container_provider}
    )


reports_container = Container(groups=[Reports])
reports_request = reports_container.build_child_container(scope=Scope.REQUEST)

assert reports_request.resolve(Reporter).di is reports_request
```

### Which container you get

`resolve(Container)` returns the container you call it on. A creator receives the container at its
factory's own scope, which is not always the one you called: an APP-scoped factory resolved from a
REQUEST container gets the APP container, because that is where it is built.

```python
class AppJobRunner(JobRunner): ...


class AppJobs(Group):
    runner = providers.Factory(AppJobRunner, scope=Scope.APP)


root = Container(groups=[AppJobs])
child = root.build_child_container(scope=Scope.REQUEST)

assert child.resolve(Container) is child
assert child.resolve(AppJobRunner).container is root
```

`container_provider` is a prebuilt instance of a private class, so there is nothing to construct.
It is always APP-scoped and ignores a group's default scope.

## Registering providers after construction

`container.add_providers(*providers)` registers more providers on a root container after it is
built. Framework integrations use it to register their context providers. It raises
`ChildContainerRegistrationError` on a child, and `DuplicateProviderTypeError` when a provider's
type is already registered. It does not validate, and it clears the validated state, so call
`validate()` after the last registration. See
[Writing an integration](../integrations/writing-integrations.md#the-contract) for the full contract.

## Looking up a provider

`container.find_provider(SomeType)` returns the provider registered for `SomeType`, or `None` when
nothing is. Every container in a tree sees the same providers, so a child answers the same as its
root. The lookup ignores overrides and the closed state, and it never resolves anything:

<!-- invisible-code-block: python
class UserRepository: ...


app_container.add_providers(providers.Factory(UserRepository, scope=Scope.REQUEST))
request_container = app_container.build_child_container(scope=Scope.REQUEST)
-->

```python
provider = request_container.find_provider(UserRepository)
if provider is not None:
    repository = request_container.resolve_provider(provider)
```

## See also

- [Context providers](context.md#context-propagation) — how context values reach (and don't
  reach) a `ContextProvider`.
- [Scopes](scopes.md) — the scope model and child containers.
- [Advanced / low-level API](advanced-api.md) — the public modules, `find_container`,
  `parent_container` and `Group.get_providers()`.
