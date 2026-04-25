# Usage with `Typer`

## How to use

1. Install `modern-di-typer`:

=== "uv"

      ```bash
      uv add modern-di-typer
      ```

=== "pip"

      ```bash
      pip install modern-di-typer
      ```

=== "poetry"

      ```bash
      poetry add modern-di-typer
      ```

2. Apply this code example to your application:

```python
import datetime
import typing

import modern_di
import modern_di_typer
import typer
from modern_di import Container, Group, Scope, providers


app = typer.Typer()


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=create_singleton,
        cache_settings=providers.CacheSettings()
    )


ALL_GROUPS = [AppGroup]

container = Container(groups=ALL_GROUPS)
modern_di_typer.setup_di(app, container)


@app.command()
@modern_di_typer.inject
def my_command(
    instance: typing.Annotated[
        datetime.datetime,
        modern_di_typer.FromDI(datetime.datetime),  # Resolve by type instead of provider
    ],
) -> None:
    typer.echo(instance)


if __name__ == "__main__":
    with container:
        app()
```

## Action scope

To resolve `Scope.ACTION` dependencies, inject `modern_di.Container` — `@inject` supplies the
`REQUEST`-scoped container it creates per invocation. Call `build_child_container()` on it to enter
`ACTION` scope:

```python
import modern_di
import modern_di_typer
import typing
from modern_di import Group, Scope, providers


class AppGroup(Group):
    job = providers.Factory(scope=Scope.ACTION, creator=..., bound_type=None)


@app.command()
@modern_di_typer.inject
def run_job(
    container: typing.Annotated[modern_di.Container, modern_di_typer.FromDI(modern_di.Container)],
) -> None:
    with container.build_child_container() as action_container:
        job = action_container.resolve_provider(AppGroup.job)
        job.run()
```

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Register the app-scoped container with a Typer app |
| `@inject` | Decorator that resolves `FromDI`-annotated parameters before the command runs |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]`; accepts a provider instance or a plain type |
| `fetch_di_container(ctx)` | Returns the app-scoped container from `ctx.obj` |
