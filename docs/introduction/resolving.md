# Resolving dependencies

`modern-di` resolves a dependency in two ways, and both cost the same:

- By type, with `container.resolve(SomeType)`. The container looks up the provider whose
  `bound_type` is `SomeType`. Handlers and creator signatures use this.
- By provider reference, with `container.resolve_provider(Dependencies.some_provider)`. This reaches
  a provider that has no type to look it up by: two providers cannot share a `bound_type`, so the
  second one needs `bound_type=None` (see [DuplicateProviderTypeError](../troubleshooting/duplicate-type-error.md)).

Prefer `resolve`. Code that resolves by type depends only on the type, not on the `Group` that
declares the provider, and an override applies to both calls alike.

## Automatic sub-dependency resolution

A `Factory`'s creator function or class constructor is introspected when the factory is declared.
For each parameter with a type annotation, the container looks for a provider whose `bound_type`
matches and injects the resolved value. A parameter with a default keeps its default when no
provider matches. Values passed in `kwargs` take precedence over both (see
[kwargs](../providers/factories.md#kwargs)).

```python
import dataclasses
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DatabaseConfig:
    host: str
    port: int


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DatabaseConnection:
    config: DatabaseConfig    # auto-resolved by type
    timeout: int = 30         # uses default if unresolvable


class Dependencies(Group):
    db_config = providers.Factory(
        DatabaseConfig,
        scope=Scope.APP,
        kwargs={"host": "localhost", "port": 5432},
    )
    db_connection = providers.Factory(DatabaseConnection, scope=Scope.APP, cache=True)


container = Container(groups=[Dependencies])
container.validate()

connection = container.resolve(DatabaseConnection)
assert connection.config.host == "localhost"
assert connection.timeout == 30
assert container.resolve(DatabaseConnection) is connection
```

## Unions and optional parameters

For a parameter typed `A | B`, the container injects the first member, left to right, that has a
registered provider. Use a concrete annotation, or pass the value in `kwargs`, if you need a
specific one ([union type parameters](../providers/factories.md#union-type-parameters)).

A parameter typed `X | None` with no provider for `X` and no default receives `None` instead of
raising. That includes the case where you meant to register the provider and forgot: neither
`resolve()` nor `validate()` reports it. Annotate a dependency that must always be present as
`X`, not `X | None` ([optional parameters](../providers/factories.md#optional-parameters)).

## When resolution fails

- `resolve(SomeType)` with no provider bound to `SomeType` raises `ProviderNotRegisteredError`
  (see [No provider registered for type](../troubleshooting/missing-provider.md)).
- A creator parameter that nothing can satisfy raises `ArgumentResolutionError`, which names the
  whole dependency chain (see [ArgumentResolutionError](../troubleshooting/argument-resolution-error.md)).

`container.validate()` reports the second kind for the whole graph at once, so call it at startup or
in one test.

## Which container resolves

A container resolves providers of its own scope and of every outer one. A REQUEST-scoped provider
resolves from a REQUEST child, built with `container.build_child_container(scope=Scope.REQUEST)`;
resolving it from the APP root raises `ScopeNotInitializedError`. See [Scopes](../providers/scopes.md).

## See also

- [Scopes](../providers/scopes.md): the scope chain governs which container resolves which provider.
- [Lifecycle](../providers/lifecycle.md): `container.validate()` catches resolution problems at startup.
- [Factories: `bound_type`](../providers/factories.md#bound_type): how the type lookup key is set, and how to opt out.
