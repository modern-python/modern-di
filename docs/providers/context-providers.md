# Context Providers

## ContextProvider

ContextProvider is a provider type that allows injecting context values into dependencies. This is particularly useful for injecting framework-specific objects like requests, websockets, etc.

ContextProvider makes context data available to other providers in your dependency graph by extracting values from the container's context.

### Basic Usage with `FastAPI`

```python
from modern_di import Group, Container, Scope, providers
import fastapi
import modern_di_fastapi


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
# Setup DI with your groups
app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, Container(groups=ALL_GROUPS))
```
