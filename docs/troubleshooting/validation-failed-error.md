# ValidationFailedError

## Symptom

Raised by `Container.validate()`, rendering a report grouped by
error class name, with the count of each kind and every individual issue indented underneath. It is
an `ExceptionGroup`, so a traceback also shows each issue below the report.

## Cause

The provider graph has one or more problems: a circular dependency, a provider depending on a
deeper-scoped one, a creator parameter with no way to be resolved, or an alias whose source type has
no registered provider. `validate()` collects every
issue across the whole graph in one pass rather than stopping at the first one, so `.exceptions`
may hold several distinct exception types at once.

## Fix

Inspect `.exceptions` to see every underlying issue, or read the grouped `str()` report directly. Each
group is one of `CircularDependencyError`, `InvalidScopeDependencyError`, `ScopeEnumMismatchError`,
`ArgumentResolutionError`, or `AliasSourceNotRegisteredError` today. Fix each one; their own pages cover the specific cause and
remedy:

```python
try:
    container.validate()
except exceptions.ValidationFailedError as exc:
    for error in exc.exceptions:
        print(type(error).__name__, error)
```

To handle one kind of issue and let the rest propagate, use `except*`:

```python
try:
    container.validate()
except* exceptions.ArgumentResolutionError as group:
    for error in group.exceptions:
        print("unresolvable parameter:", error.parameter_name)
```

What `except*` does not catch is raised again as a `ValidationFailedError` holding only the
remaining issues.

Call `validate()` explicitly at startup, before the first real request: it turns graph bugs into a
single startup-time failure instead of scattered runtime surprises. Nothing calls it for you: not
construction, not `open()`, not `resolve()`.

## See also

- [Lifecycle: validation](../providers/lifecycle.md#validation).
- The underlying issue kinds: [Circular dependency](circular-dependency.md), [Scope chain violation](scope-chain.md), [Scope enum mismatch](scope-enum-mismatch-error.md), [Argument resolution error](argument-resolution-error.md), [Alias source not registered](alias-source-not-registered-error.md).
