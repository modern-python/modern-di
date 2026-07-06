# Circular Dependency Error

This error occurs when providers form a dependency cycle, meaning A depends on B which depends back on A (directly or through intermediate providers).

## Understanding the Error

When you see this error:

```
Container.validate() found 1 issue(s): CircularDependencyError

CircularDependencyError (1):
  - Circular dependency detected:
      ServiceA
      └─> ServiceB
          └─> ServiceA
    Check your provider graph for unintended cycles.
```

It means the listed providers form a cycle that cannot be resolved.

## How to Detect

**Without `validate()`**, resolving from an unvalidated cyclic graph still raises
`CircularDependencyError`: the first resolve overflows the stack, and `Container.resolve_provider`
catches that `RecursionError`, re-walks the static graph from the failing provider, and — since a
cycle is reachable — raises `CircularDependencyError` (with the same cycle-path rendering shown
above) `from` the original `RecursionError`. A creator that merely recurses on its own, with no
actual cycle in the provider graph, still raises the original `RecursionError` unchanged — only a
real static cycle gets converted.

Calling `validate()` up front finds the *same* cycle earlier, and finds *every* issue in the graph
in one pass (not just the one a particular resolve happens to hit) — prefer it in development:

```python
from modern_di import Container

# Option 1: validate at creation
container = Container(groups=[MyGroup], validate=True)

# Option 2: validate explicitly (validate=False silences the construction-time
# UnvalidatedContainerWarning since validate() below runs the same check manually)
container = Container(groups=[MyGroup], validate=False)
container.validate()
```

## How to Resolve

1. **Break the cycle with an interface/protocol** - introduce an abstraction that one side depends on instead of the concrete type
2. **Use `kwargs` to inject one dependency manually** - pass a factory or value via `kwargs` instead of relying on automatic resolution
3. **Restructure your dependencies** - extract shared logic into a third provider that both can depend on without forming a cycle

## See also

- [Errors and exceptions](../providers/errors-and-exceptions.md)
- [Lifecycle](../providers/lifecycle.md) — the validation section.
