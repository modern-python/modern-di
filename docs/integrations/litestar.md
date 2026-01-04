# Usage with `Litestar`

*More advanced example of usage with LiteStar - [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)*

## How to use

1. Install `modern-di-litestar`:

=== "uv"

      ```bash
      uv add modern-di-litestar
      ```

=== "pip"

      ```bash
      pip install modern-di-litestar
      ```

=== "poetry"

      ```bash
      poetry add modern-di-litestar
      ```

2. Apply this code example to your application:
```python
import datetime
import typing

from litestar import Litestar, get
import modern_di_litestar
from modern_di import Container, Group, Scope, providers


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Singleton(Scope.APP, create_singleton)


# Register your groups
ALL_GROUPS = [AppGroup]


@get("/", dependencies={"injected": modern_di_litestar.FromDI(datetime.datetime)})  # Resolve by type
async def index(injected: datetime.datetime) -> str:
    return injected.isoformat()


app = Litestar(
    route_handlers=[index],
    plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=ALL_GROUPS))],
)
```

## Websockets

Usually our application uses only two scopes: `APP` and `REQUEST`.

But when websockets are used, `SESSION` scope is used as well:
- for the lifetime of websocket-connection we have `SESSION` scope
- for each message we have `REQUEST` scope

`APP` → `SESSION` → `REQUEST`

`SESSION` scope is entered automatically.
`REQUEST` scope must be entered manually:

```python
import litestar
from modern_di import Container, Scope
import modern_di_litestar


app = litestar.Litestar(plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=ALL_GROUPS))])


@litestar.websocket_listener("/ws")
async def websocket_handler(
    data: str,
    di_container: Container
) -> None:
    request_container = di_container.build_child_container(scope=Scope.REQUEST)
    # REQUEST scope is entered here
    # You can resolve dependencies here
    pass

app.register(websocket_handler)
```
