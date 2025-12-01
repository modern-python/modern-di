# Context Providers

## ContextProvider

ContextProvider is a provider type that allows injecting context values into dependencies. This is particularly useful for injecting framework-specific objects like requests, websockets, etc.

ContextProvider makes context data available to other providers in your dependency graph by extracting values from the container's context.

### Basic Usage

```python
from modern_di import Group, AsyncContainer, Scope, providers
import fastapi


class Dependencies(Group):
    # ContextProvider takes a scope and a type annotation
    request = providers.ContextProvider(Scope.REQUEST, fastapi.Request)


# Create container with context
ALL_GROUPS = [Dependencies]
container = AsyncContainer(groups=ALL_GROUPS)
container.enter()

# Close container when done
container.close()
```

### Using ContextProvider with Factory

ContextProvider can be used with any provider type that accepts dependencies, with Factory being one of the simplest examples:

```python
from modern_di import Group, AsyncContainer, Scope, providers
import fastapi


def create_request_info(request: fastapi.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class Dependencies(Group):
    # ContextProvider extracts the request from context
    request = providers.ContextProvider(Scope.REQUEST, fastapi.Request)

    # Factory uses the request from context
    request_info = providers.Factory(
        Scope.REQUEST,
        create_request_info,
        request=request.cast,
    )


# Create container with context
ALL_GROUPS = [Dependencies]
container = AsyncContainer(groups=ALL_GROUPS)
container.enter()

# To resolve with actual context, you would pass context when building child containers
# Close container when done
container.close()
```

### Framework Integration

In web framework integrations, ContextProvider is typically used to inject framework-specific objects like requests:

```python
from modern_di import Group, Scope, providers
import fastapi


class WebDependencies(Group):
    request = providers.ContextProvider(Scope.REQUEST, fastapi.Request)
    # Other providers can now use the request object through request.cast
```
