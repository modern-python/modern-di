# Usage with `Typer`

## How to use

### 1. Install `modern-di-typer`

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

### 2. Apply to your application

```python
import dataclasses
import typing

import modern_di_typer
import typer
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    environment: str = "production"


@dataclasses.dataclass(kw_only=True, slots=True)
class HealthReporter:
    settings: Settings    # auto-injected by type

    def report(self) -> str:
        return f"healthy in {self.settings.environment}"


class AppGroup(Group):
    settings = providers.Factory(
        scope=Scope.APP,
        creator=Settings,
        cache=True,
    )
    health_reporter = providers.Factory(
        scope=Scope.REQUEST,
        creator=HealthReporter,
    )


app = typer.Typer()
container = Container(groups=[AppGroup], validate=True)
modern_di_typer.setup_di(app, container)


@app.command()
@modern_di_typer.inject
def status(
    reporter: typing.Annotated[
        HealthReporter,
        modern_di_typer.FromDI(HealthReporter),    # resolve by type
    ],
) -> None:
    typer.echo(reporter.report())


if __name__ == "__main__":
    with container:                                # runs APP-scope finalizers on exit
        app()
```

`@modern_di_typer.inject` builds a `REQUEST` child container for each command invocation and resolves `FromDI`-annotated parameters from it. The outer `with container:` ensures APP-scope finalizers run when the CLI exits.

## Action scope

To resolve `Scope.ACTION` dependencies, inject `modern_di.Container` — `@inject` supplies the
`REQUEST`-scoped container it creates per invocation. Call `build_child_container()` on it to enter
`ACTION` scope:

Building on the first example's `app` and `container`:

```python
import modern_di
import modern_di_typer
import typing
from modern_di import Group, Scope, providers


class Job:
    def run(self) -> None: ...


class AppGroup(Group):
    job = providers.Factory(scope=Scope.ACTION, creator=Job, bound_type=None)


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
