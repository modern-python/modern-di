# Factories

A `Factory` calls its creator, a class or function, and fills the creator's parameters by type
from the container. Without `cache`, every resolve calls the creator again:

```python
import dataclasses

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    api_url: str = "https://api.example.com"


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ApiClient:
    settings: Settings


class Dependencies(Group):
    settings = providers.Factory(Settings, cache=True)
    api_client = providers.Factory(ApiClient)


container = Container(groups=[Dependencies])
client = container.resolve(ApiClient)

assert client.settings is container.resolve(Settings)  # cached: one instance
assert container.resolve(ApiClient) is not client  # uncached: a new one per resolve
```

`api_url` keeps its default because no provider is registered for `str`.
[Resolving dependencies](../introduction/resolving.md) covers how parameters are matched.

## Cached factories

With `cache=True`, a factory builds its instance once per container at its scope and returns that
instance on every later resolve. This is the singleton idiom, and `modern-di` has no separate
`Singleton` provider: `Scope.APP` gives one instance per process, `Scope.REQUEST` one per request.
[Where is Singleton?](../introduction/comparison.md#where-is-singleton-cross-framework-vocabulary)
maps the names other DI frameworks use.

The cache is thread-safe. When several threads resolve the same cached factory at once, one
instance is created and its dependencies are resolved once for it. The other threads wait for that
instance, and resolves of other cached factories do not wait.

To clean the instance up when its container closes, pass
`cache=providers.CacheSettings(finalizer=...)`; see
[Caching and finalizers](lifecycle.md#caching-and-finalizers).

## Parameters

`Factory(creator, *, scope, bound_type, kwargs=None, cache=False, skip_creator_parsing=False)`.
Everything after `creator` is keyword-only, and `creator` can be passed as `creator=` too. The
defaults for `scope` and `bound_type` are described below.

### creator

The callable, a function or a class, that builds the instance. `modern-di` reads its signature to:

1. Find the return type, which becomes the `bound_type` unless you set one.
2. Find the parameter names and types to wire by type.

### scope

The provider's lifetime. Without `scope=`, the provider takes its group's default scope, or
`Scope.APP` when the group sets none; see
[Group-level default scope](scopes.md#group-level-default-scope).
[Scopes](scopes.md) covers the five scopes and the dependency rule.

### bound_type

The type the provider is registered under. `container.resolve(SomeType)` looks it up by this type,
and a parameter annotated with it is wired to this provider. It defaults to the creator's return
annotation.

`bound_type=None` makes the provider resolvable only by reference: through
`container.resolve_provider(Dependencies.some_provider)` or as a value in another factory's
[`kwargs`](#kwargs). `container.validate()` does not check such a provider unless a provider
registered by type depends on it, so a broken one fails on its first resolve instead
([#656](https://github.com/modern-python/modern-di/issues/656)).

A `NewType` or a `type X = ...` alias is a bound type of its own. A provider declared with
`bound_type=UserId` (or a creator returning `UserId`) is what a `user_id: UserId` parameter
resolves to; a provider bound to the underlying `int` is not. Pass the same object to
`container.resolve()` or `container.find_provider()` to look the provider up by it.
`container.resolve(UserId)` is typed `Any`, so annotate the variable you assign it to. mypy, which
treats a `NewType` as a class, types it `UserId`.

A return annotation that is a union of several types (`-> A | B`) gives no bound type, and
`Factory(...)` emits a `UserWarning`. Pass `bound_type=` with the type to register under, or
`bound_type=None` if the provider is only resolved by reference.

### kwargs

Values for creator parameters, by name. A parameter named in `kwargs` is not wired by type.

- A plain value is passed as is.
- A provider is resolved when the factory resolves, and its result is passed. Use it to pick a
  specific provider for one parameter, or to wire arguments under `skip_creator_parsing=True`.
- A name the creator does not have raises `UnknownFactoryKwargError` when the `Factory` is
  declared.

```python
@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Backend:
    name: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Worker:
    backend: Backend
    retries: int


class WorkerDependencies(Group):
    primary = providers.Factory(Backend, kwargs={"name": "primary"}, cache=True)
    replica = providers.Factory(Backend, kwargs={"name": "replica"}, bound_type=None, cache=True)
    worker = providers.Factory(Worker, kwargs={"backend": replica, "retries": 3})


container = Container(groups=[WorkerDependencies])
assert container.resolve(Worker).backend.name == "replica"
```

`replica` has `bound_type=None` because two providers cannot both register under `Backend`.

### cache

`cache=True` caches with the default settings: no finalizer, and the instance is dropped when the
container closes. `cache=providers.CacheSettings(...)` sets a finalizer or `clear_cache`; see
[Lifecycle](lifecycle.md). The default, `cache=False`, creates a new instance on every resolve. Any
other value, `None` included, raises `TypeError`.

### skip_creator_parsing

Turns off wiring. With `skip_creator_parsing=True`:

- No parameter is wired by type, so every required argument must come from `kwargs`.
- The return annotation is not read, so `bound_type` is `None` unless you pass one.

Without an explicit `bound_type`, `Factory(...)` emits a `UserWarning` saying the provider cannot be
resolved by type. Pass `bound_type=SomeType` to register it, or `bound_type=None` to confirm it is
resolved by reference only.

## Resolution behavior

### Union type parameters

When a parameter is annotated with a union type (e.g. `dep: A | B`), `modern-di` resolves the **first registered type** that matches. The order is determined by how types appear in the union left-to-right. If you rely on a specific type being injected, prefer a concrete type annotation over a union.

### Optional parameters

When a parameter is annotated as `X | None` (or `Optional[X]`), the parameter is treated as optional:

- If a provider for `X` is registered, that provider is resolved and injected as usual.
- If no provider for `X` is registered and the parameter has no default, `None` is injected: no error is raised, and `container.validate()` will not flag the parameter.

This also applies to multi-member optional unions (`A | B | None`): the first registered member is injected, otherwise `None`.

!!! note "Trade-off"
    This is a convenience, but it removes a safety net: if you *intended* to register a provider for an optional dependency and forgot, neither `resolve()` nor `validate()` will report it; the parameter silently receives `None`. For dependencies that must always be present, prefer a non-optional annotation (`dep: X`), which raises `ArgumentResolutionError` when unregistered and is flagged by `validate()`.

```python
import dataclasses

from modern_di import Group, Container, Scope, providers


class Cache: ...


@dataclasses.dataclass
class Service:
    cache: Cache | None  # injected if a Cache provider exists, else None


class Dependencies(Group):
    service = providers.Factory(Service, scope=Scope.APP)


container = Container(groups=[Dependencies])
service = container.resolve(Service)
assert service.cache is None  # no Cache provider registered -> None injected
```

### Creator-signature support matrix

The table below summarises how `modern-di` handles each parameter shape during **declaration** (when the `Factory` object is constructed) and **resolution** (when `container.resolve` is called). "Escapes" means the parameter is silently excluded from automatic wiring and must be covered by `kwargs` or a default.

| Parameter shape | Behaviour | When it fails |
|---|---|---|
| `param: SomeClass` (plain type annotation with a registered provider) | Resolved and injected automatically. | `ArgumentResolutionError` at resolve if no provider is registered and there is no default. |
| `param: X | None` / `Optional[X]` | Provider injected if one is registered; otherwise `None`. | Never fails; see [Optional parameters](#optional-parameters). |
| `param: A | B` (union without `None`) | First registered type from the union is injected. A member that is itself a parameterized generic (e.g. `int | list[X]`) degrades to its bare origin (`list`) for matching purposes; see the note below. | `ArgumentResolutionError` at resolve if neither `A` nor `B` has a registered provider. |
| `param: UserId` (a `NewType`) or `param: Alias` (a `type Alias = ...` statement, Python 3.12+) | Resolved from the provider whose `bound_type` is that `NewType` or alias. The underlying type is not looked up. | `ArgumentResolutionError` at resolve if no provider is bound to it and there is no default. |
| `param: list[X]` / any parameterized generic, **outside a union** | **`UnsupportedCreatorParameterError` at declaration** unless the parameter has a default value or is covered by `kwargs`. | Raised at `Factory(...)` call time. |
| Positional-only param (`def f(x: T, /)`) | **`UnsupportedCreatorParameterError` at declaration** unless the parameter has a default (in which case it is silently skipped). | Raised at `Factory(...)` call time. |
| Unannotated param (`def f(x)`) | Parsed but unresolvable by type. | `ArgumentResolutionError` at resolve unless covered by `kwargs`. |
| Signature whose hints `get_type_hints` cannot resolve (e.g. a forward reference to an undefined name, or `functools.partial` on Python < 3.14) | `UserWarning` is emitted and type-based wiring is skipped; parameters are still parsed (as unannotated). Silence by passing `skip_creator_parsing=True` and an explicit `bound_type`. | A required unannotated param with no provider/default raises `ArgumentResolutionError` at resolve unless covered by `kwargs` (a parameterized-generic or positional-only param still raises `UnsupportedCreatorParameterError` at declaration). |
| `skip_creator_parsing=True` | No wiring at all; every required argument must be supplied via `kwargs`. | `CreatorCallError` at resolve for any missing required argument. |

A parameterized generic used *inside* a union (`param: int | list[X]`) is the one exception to
the "parameterized generic raises at declaration" row above: the member degrades to its bare
origin type like any other union member, so it can match a provider registered for `list`. The
element type `X` is not checked, so don't rely on it to route only correctly typed collections.

If a parameter shape would raise at declaration, there are three ways around it, in order of preference:

1. Give the parameter a default value (`def f(items: list[X] | None = None)`).
2. Supply the value via `kwargs={"items": []}` at `Factory` declaration time.
3. Pass `skip_creator_parsing=True` (and supply all required args via `kwargs`).

Routes 2 and 3 pass the value by keyword, so they only work for a parameterized generic. A
positional-only parameter needs route 1: with route 2 it still raises
`UnsupportedCreatorParameterError`, and with route 3 it raises `CreatorCallError` at resolve.


### Creator-failure semantics

If a creator raises during resolution:

- Nothing is cached, even with `cache` set.
- The next resolve calls the creator again, so a creator that fails transiently succeeds once the
  underlying condition is fixed.
- Dependencies resolved before the creator raised are not rolled back. They stay cached in their
  containers and are finalized when those containers close.

```python
class Connection:
    attempts = 0

    def __init__(self) -> None:
        Connection.attempts += 1
        if Connection.attempts == 1:
            raise ConnectionError("transient failure")


class ConnectionDependencies(Group):
    connection = providers.Factory(Connection, cache=True)


container = Container(groups=[ConnectionDependencies])

try:
    container.resolve(Connection)
except ConnectionError:
    pass  # the first call fails and nothing is cached

connection = container.resolve(Connection)  # the retry succeeds
assert connection is container.resolve(Connection)  # and is cached now
```

## See also

- [Resolving dependencies](../introduction/resolving.md): how parameters are matched to providers.
- [Lifecycle](lifecycle.md): finalizers, closing, and `validate()`.
- [Scopes](scopes.md): which container caches an instance.
- [Alias](alias.md): making one type resolve to another type's provider, such as a `Protocol` to its implementation.
