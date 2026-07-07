# ValidationFailedError

**Symptom**

Raised by `Container.validate()` (or `Container(..., validate=True)`), rendering a report grouped by
error class name, with the count of each kind and every individual issue indented underneath.

**Cause**

The provider graph has one or more problems: a circular dependency, a provider depending on a
deeper-scoped one, a creator parameter with no way to be resolved, or an alias whose source type has
no registered provider. `validate()` collects **every**
issue across the whole graph in one pass rather than stopping at the first one, so `.errors` (a
`list[Exception]`) may hold several distinct exception types at once.

**Fix**

Inspect `.errors` to see every underlying issue, or read the grouped `str()` report directly — each
group is one of `CircularDependencyError`, `InvalidScopeDependencyError`, `ArgumentResolutionError`,
or `AliasSourceNotRegisteredError` today. Fix each one; their own pages cover the specific cause and
remedy:

```python
try:
    container.validate()
except exceptions.ValidationFailedError as exc:
    for error in exc.errors:
        print(type(error).__name__, error)
```

Running `validate()` (or passing `validate=True`) at startup, before the first real request, is the
whole point — it turns graph bugs into a single startup-time failure instead of scattered runtime
surprises.

## See also

- [Lifecycle: validation](../providers/lifecycle.md#validation).
- [Circular dependency](circular-dependency.md), [Scope chain violation](scope-chain.md), [Argument resolution error](argument-resolution-error.md), [Alias source not registered](alias-source-not-registered-error.md) — the underlying issue kinds.
