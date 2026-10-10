# Usage with `Typer`

`setup_di` attaches the container to a `typer.Typer` app, and `@inject` builds a `Scope.REQUEST`
child container for each command run. The root container is yours to close. `setup_di` needs a
`typer.Typer`: a plain Click group fails with `AttributeError`, and there is no Click adapter.

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
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings   # APP-scoped, injected by type

    def render(self) -> str:
        return f"service={self.settings.service_name}"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


app = typer.Typer()
container = Container(groups=[AppGroup])
modern_di_typer.setup_di(app, container)
container.validate()  # fails fast on a broken graph before the CLI runs


@app.command()
@modern_di_typer.inject
def status(
    report: typing.Annotated[Report, modern_di_typer.FromDI(Report)],   # resolve by type
) -> None:
    typer.echo(report.render())


if __name__ == "__main__":
    with container:                                # runs APP-scope finalizers on exit
        app()
```

## Scopes

`@inject` builds one `Scope.REQUEST` child container per command run, even for a command with no
`FromDI` parameter, and closes it with `close_sync()` when the command returns or raises. An async
finalizer on a REQUEST-scoped provider therefore fails the command with `FinalizerError`.

## Root container lifecycle

Typer has no startup or shutdown hook, so the integration never closes the root container. Wrap
the call to `app()` in `with container:`, as above. Typer ends the process with `sys.exit`, which
passes through the `with` block, and the block closes the root with `close_sync()` and runs
APP-scoped finalizers. As with the per-command child, an async finalizer fails there with
`FinalizerError`.

## Framework context objects

The integration registers no context provider. A command reads its own arguments, and a command
that needs the Click context declares a `typer.Context` parameter.

## Action scope

`modern_di_typer.action_scope(ctx)` opens a `Scope.ACTION` child of the command's container and
closes it on exit. The command must be decorated with `@inject` and declare a `typer.Context`
parameter; without `@inject`, `action_scope` raises `RuntimeError`. Building on the first
example's `app`:

```python
class Job:
    def run(self) -> None: ...


class JobGroup(Group):
    job = providers.Factory(Job, scope=Scope.ACTION, bound_type=None)


@app.command()
@modern_di_typer.inject
def run_job(ctx: typer.Context) -> None:
    with modern_di_typer.action_scope(ctx) as action_container:
        action_container.resolve_provider(JobGroup.job).run()
```

The command can also inject the REQUEST container itself with
`FromDI(modern_di.Container)` and call `build_child_container()` on it.

## Testing

Typer's `CliRunner` invokes the app in-process. It does not close the root container, so close
it yourself when the test needs APP-scoped finalizers to run:

```python
from typer.testing import CliRunner

result = CliRunner().invoke(app, ["status"])
assert result.exit_code == 0
assert result.output == "service=catalog\n"
```

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Lifecycle](../providers/lifecycle.md): finalizers and container teardown.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Attaches the root container to a `typer.Typer` app and returns it. |
| `@inject` | Builds a `Scope.REQUEST` child container per command run, resolves `FromDI`-annotated parameters from it, and closes it with `close_sync()`. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in command signatures; accepts a provider instance or a plain type. |
| `fetch_di_container(ctx)` | Returns the root container attached by `setup_di`, from any command, including those of nested `add_typer` sub-apps. Raises `RuntimeError` naming `setup_di` when the app has none. |
| `action_scope(ctx)` | Context manager that yields a `Scope.ACTION` child of the container `@inject` built for the command, and closes it on exit. Raises `RuntimeError` when the command isn't decorated with `@inject`. |
