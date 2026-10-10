# CircularDependencyError

## Symptom

Resolving a provider that sits on a cycle raises:

```
modern_di.exceptions.resolution.CircularDependencyError: Circular dependency detected:
  APP  ServiceA (myapp.cycle:6)
  APP  └─> ServiceB (myapp.cycle:11)
  APP      └─> ServiceA (myapp.cycle:6)
Check your provider graph for unintended cycles.
See: https://modern-di.modern-python.org/troubleshooting/circular-dependency/
```

`container.validate()` reports the same cycle inside [`ValidationFailedError`](validation-failed-error.md):

```
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 1 issue(s): CircularDependencyError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.resolution.CircularDependencyError: Circular dependency detected:
    |   APP  ServiceA (myapp.cycle:6)
    |   APP  └─> ServiceB (myapp.cycle:11)
    |   APP      └─> ServiceA (myapp.cycle:6)
    | Check your provider graph for unintended cycles.
    | See: https://modern-di.modern-python.org/troubleshooting/circular-dependency/
    +------------------------------------
```

Each line is one hop of the cycle, with its scope and, for a `Factory`, the module and line where its
creator is declared. `.steps` holds the hops, and `.cycle_path` and `.cycle_locations` hold their
names and locations.

## Cause

The providers form a loop: A depends on B, which depends back on A, directly or through other
providers. The loop can run through a parameter's type annotation, a `kwargs` entry that holds a
provider, or an `Alias`.

### The runtime cycle guard (without `validate()`)

Resolving from an unvalidated cyclic graph still raises `CircularDependencyError`: the first
resolve overflows the stack, and `Container.resolve_provider` catches that `RecursionError`,
re-walks the static graph from the failing provider, and, since a cycle is reachable, raises
`CircularDependencyError` (with the same cycle-path rendering shown above) `from` the original
`RecursionError`. A creator that recurses on its own, with no cycle in the provider graph, still
raises the original `RecursionError` unchanged. This guard runs on every resolve, whether or not
`validate()` was ever called.

The guard covers resolution on one thread. Each cached factory locks its cache item while it is
created, so two threads that cold-resolve different providers of the same cycle at the same time
can each hold one of those locks and wait for the other forever, and neither reaches the guard.
If the graph might have a cycle, call `validate()` at startup, before any thread resolves.

## Fix

Find every cycle at startup with `validate()`. It walks the whole graph in one pass and reports each
issue it finds, where a resolve reports only the cycle it happens to hit:

<!-- invisible-code-block: python
from __future__ import annotations

from typing import Protocol

from modern_di import Group, Scope, providers


class ServiceA:
    def __init__(self, b: ServiceB) -> None:
        self.b = b


class ServiceB:
    def __init__(self, a: ServiceA) -> None:
        self.a = a


class MyGroup(Group):
    service_a = providers.Factory(ServiceA, scope=Scope.APP)
    service_b = providers.Factory(ServiceB, scope=Scope.APP)
-->

<!-- raises: ValidationFailedError -->

```python
from modern_di import Container

container = Container(groups=[MyGroup])
container.validate()
```

Then break the loop with one of these:

1. Pass one side a static value through `kwargs`. Only a value breaks the cycle: a `kwargs` entry
   that holds a provider is still an edge of the graph, so `kwargs={"a": service_a}` keeps the loop.
2. Have one side depend on an interface whose provider sits outside the cycle. An `Alias` that maps
   the interface back to a provider on the cycle keeps the loop.
3. Move the logic both sides need into a third provider that both depend on.

Option 2, with `ServiceB` taking a `Notifier` that `EmailNotifier` provides instead of `ServiceA`:

```python
class Notifier(Protocol): ...


class EmailNotifier: ...


class ServiceB:
    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier


class ServiceA:
    def __init__(self, b: ServiceB) -> None:
        self.b = b


class Fixed(Group):
    email = providers.Factory(EmailNotifier, scope=Scope.APP)
    notifier = providers.Alias(EmailNotifier, bound_type=Notifier)
    service_a = providers.Factory(ServiceA, scope=Scope.APP)
    service_b = providers.Factory(ServiceB, scope=Scope.APP)


container = Container(groups=[Fixed])
container.validate()
```

## See also

- [Errors and exceptions](../providers/errors-and-exceptions.md): where this error sits in the hierarchy.
- [Lifecycle: validation](../providers/lifecycle.md#validation): what `validate()` checks.
- [ValidationFailedError](validation-failed-error.md): how `validate()` groups the errors it finds.
