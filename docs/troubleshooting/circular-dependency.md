# CircularDependencyError

This error occurs when providers form a dependency cycle, meaning A depends on B which depends back on A (directly or through intermediate providers).

## Symptom

When you see this error:

```
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 1 issue(s): CircularDependencyError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.resolution.CircularDependencyError: Circular dependency detected:
    |   APP  ServiceA (myapp.cycle:6)
    |   APP  └─> ServiceB (myapp.cycle:10)
    |   APP      └─> ServiceA (myapp.cycle:6)
    | Check your provider graph for unintended cycles.
    | See: https://modern-di.modern-python.org/troubleshooting/circular-dependency/
    +------------------------------------
```

It means the listed providers form a cycle that cannot be resolved. Each hop in the arrow chain may also end with a pointer to where that provider was declared (module and line number), making it easier to locate the offending provider in a large codebase.

## How to detect

### The runtime cycle guard (without `validate()`)

Resolving from an unvalidated cyclic graph still raises `CircularDependencyError`: the first
resolve overflows the stack, and `Container.resolve_provider` catches that `RecursionError`,
re-walks the static graph from the failing provider, and, since a cycle is reachable, raises
`CircularDependencyError` (with the same cycle-path rendering shown above) `from` the original
`RecursionError`. A creator that merely recurses on its own, with no actual cycle in the provider
graph, still raises the original `RecursionError` unchanged. This guard runs on every resolve, whether or not `validate()` was ever called.

The guard covers resolution on one thread. Each cached factory locks its cache item while it is
created, so two threads that cold-resolve different providers of the same cycle at the same time
can each hold one of those locks and wait for the other forever, and neither reaches the guard.
If the graph might have a cycle, call `validate()` at startup, before any thread resolves.

### Cycle detection with `validate()`

Calling `validate()` up front finds the *same* cycle earlier, and finds *every* issue in the graph
in one pass (not just the one a particular resolve happens to hit). Prefer it in development:

<!-- skip: next "fragment" -->

```python
from modern_di import Container

container = Container(groups=[MyGroup])
container.validate()  # raises ValidationFailedError (wraps CircularDependencyError) if a cycle exists
```

## Fix

1. Break the cycle by introducing an interface or protocol that one side depends on instead of the concrete type.
2. Inject one dependency manually by passing a factory or value via `kwargs` instead of relying on automatic resolution.
3. Restructure your dependencies by extracting shared logic into a third provider that both can depend on without forming a cycle.

## See also

- [Errors and exceptions](../providers/errors-and-exceptions.md)
- [Lifecycle](../providers/lifecycle.md), the validation section.
