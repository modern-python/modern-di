# Circular Dependency Error

This error occurs when providers form a dependency cycle, meaning A depends on B which depends back on A (directly or through intermediate providers).

## Understanding the Error

When you see this error:

```
ValidationFailedError: Container.validate() found 1 issue(s): CircularDependencyError
  - Circular dependency detected: ServiceA -> ServiceB -> ServiceA. Check your provider graph for unintended cycles.
```

It means the listed providers form a cycle that cannot be resolved. Without `validate()`, this would manifest as a `RecursionError` during resolution.

## How to Detect

Call `validate()` explicitly or pass `validate=True` at container creation:

```python
from modern_di import Container

# Option 1: validate at creation
container = Container(groups=[MyGroup], validate=True)

# Option 2: validate explicitly
container = Container(groups=[MyGroup])
container.validate()
```

## How to Resolve

1. **Break the cycle with an interface/protocol** - introduce an abstraction that one side depends on instead of the concrete type
2. **Use `kwargs` to inject one dependency manually** - pass a factory or value via `kwargs` instead of relying on automatic resolution
3. **Restructure your dependencies** - extract shared logic into a third provider that both can depend on without forming a cycle

## See also

- [Errors and exceptions](../providers/errors-and-exceptions.md)
- [Lifecycle](../providers/lifecycle.md) — the validation section.
