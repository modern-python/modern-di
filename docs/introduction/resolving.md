# Resolving Dependencies

Dependencies can be resolved in three ways:

1. **By provider reference** - Using `container.resolve_provider(provider)`
2. **By type** - Using `container.resolve(dependency_type=SomeType)`
3. **By name** - Using `container.resolve(dependency_name="provider_name")`

When resolving by type, the container looks for a provider whose `bound_type` matches the requested type.
By default, the `bound_type` is automatically inferred from the creator's return type annotation.

When resolving by name, the container looks for a provider with a matching attribute name in the `Group`.

## Resolving of Sub Dependencies

One of the key features of `Modern-DI` since 2.x version is the automatic resolution of sub dependencies through type annotations.
`Modern-DI` automatically analyzes the creator function or class constructor to identify its parameter types and attempts to resolve them from registered providers.

### How It Works

When a factory is created:
1. Modern-DI parses the creator's signature to identify parameter names and types
2. For each parameter with a type annotation, it searches for a registered provider that matches:
   - First by parameter type (if provided)
   - Then by parameter name (if type lookup fails)
3. If a matching provider is found, it's automatically injected when the factory is resolved
4. If no matching provider is found and no default value is provided, an error is raised

Example:

```python
import dataclasses
from modern_di import Group, Container, Scope, providers

@dataclasses.dataclass(kw_only=True, slots=True)
class DatabaseConfig:
    host: str
    port: int

@dataclasses.dataclass(kw_only=True, slots=True)
class DatabaseConnection:
    config: DatabaseConfig  # Automatically resolved by type
    timeout: int = 30  # Uses default value

class Dependencies(Group):
    db_config = providers.Factory(
        creator=DatabaseConfig,
        kwargs={"host": "localhost", "port": 5432}
    )
    db_connection = providers.Factory(
        creator=DatabaseConnection
    )

container = Container(groups=[Dependencies])
connection = container.resolve(DatabaseConnection)
assert isinstance(connection.config, DatabaseConfig)
assert connection.config.host == "localhost"
assert connection.timeout == 30
```
