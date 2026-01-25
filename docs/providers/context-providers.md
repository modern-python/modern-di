# Context Providers

## ContextProvider

ContextProvider is a provider type that allows injecting context values into dependencies. This is particularly useful for injecting framework-specific objects like requests, websockets, etc.

ContextProvider makes context data available to other providers in your dependency graph by extracting values from the container's context.

In integrations, some context objects (like `fastapi.Request`, `litestar.WebSocket`, etc.) are automatically provided.

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
    # Factory uses the request from context (automatically provided by the integration)
    request_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_request_info,
    )


# Create container with context
ALL_GROUPS = [Dependencies]
# Setup DI with your groups
app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, Container(groups=ALL_GROUPS))
```

You can resolve the context provider by type or by name:

```python
# Resolving by type
request_info_dict = container.resolve(dependency_type=dict)

# Resolving by name
request_info_dict = container.resolve(dependency_name="request_info")
```

### Manual ContextProvider Usage

You may still need to define ContextProviders manually in cases where you want to inject custom context objects that are not automatically provided by the integration:

```python
from modern_di import Group, Container, Scope, providers

# Custom context type
class CustomContext:
    def __init__(self, user_id: str, tenant_id: str) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id


def create_user_info(custom_context: CustomContext) -> dict[str, str]:
    return {
        "user_id": custom_context.user_id,
        "tenant_id": custom_context.tenant_id,
    }


class Dependencies(Group):
    # Manually defined ContextProvider for custom context
    custom_context = providers.ContextProvider(scope=Scope.REQUEST, context_type=CustomContext)

    # Factory uses the custom context
    user_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_user_info,
    )

    
# Provide custom context when building container
container = Container(groups=[Dependencies])
custom_context = CustomContext(user_id="123", tenant_id="abc")
request_container = container.build_child_container(
    scope=Scope.REQUEST,
    context={CustomContext: custom_context}
)
```
