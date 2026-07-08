# Resolving dependencies

`modern-di` exposes two ways to resolve a dependency:

- **By type** — `container.resolve(SomeType)`. The resolver finds the provider whose `bound_type` matches `SomeType`. This is what handlers and creator signatures normally use.
- **By provider reference** — `container.resolve_provider(Dependencies.some_provider)`. Resolves a specific provider directly, skipping the type lookup. Useful in tests and when two providers produce the same type.

In practice, prefer resolution by type — it lets the same code work whether you swap implementations via subclassing, `Alias`, or `override`. Reach for `resolve_provider` only when type-based resolution would be ambiguous.

## Automatic sub-dependency resolution

A `Factory`'s creator function or class constructor is introspected at declaration time. For each parameter with a type annotation, the resolver looks for a provider whose `bound_type` matches and injects the resolved value. Parameters with default values fall back to those defaults if no provider matches.

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
    db_connection = providers.Factory(DatabaseConnection, scope=Scope.APP)


container = Container(groups=[Dependencies], validate=True)

connection = container.resolve(DatabaseConnection)
assert connection.config.host == "localhost"
assert connection.timeout == 30
```

For union-typed parameters (`dep: A | B`), the resolver picks the *first* type in the union that has a registered provider. If you need a specific one, use a concrete annotation or pass the value explicitly via `kwargs`. A parameter typed `X | None` with no matching provider and no default value receives `None` rather than raising (see [Factories: Optional parameters](../providers/factories.md)).

## See also

- [Scopes](../providers/scopes.md) — the scope chain governs which container resolves which provider.
- [Lifecycle](../providers/lifecycle.md) — `Container(validate=True)` catches resolution problems at startup.
- [Factories: `bound_type`](../providers/factories.md) — how the type lookup key is set, and how to opt out.
