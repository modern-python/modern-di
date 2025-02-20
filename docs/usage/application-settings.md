# Application settings
For example, you have application settings in `pydantic_settings`
```python
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    service_name: str = "FastAPI template"
    debug: bool = False
    ...
```

You can register settings as `Singleton` in DI container

```python
from modern_di import BaseGraph, Scope, providers


class DIContainer(BaseGraph):
    settings = providers.Singleton(Scope.APP, Settings)
    some_factory = providers.Factory(Scope.APP, SomeFactory, service_name=settings.cast.service_name)
```

And when `some_factory` is resolved it will receive `service_name` attribute from `Settings`
