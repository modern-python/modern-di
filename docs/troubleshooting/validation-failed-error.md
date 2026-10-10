# ValidationFailedError

## Symptom

Raised by `Container.validate()`. Its message is one line naming each kind of issue with its count,
followed by a link to this page. It is an `ExceptionGroup`, so a traceback shows each issue in full
below that line:

```
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 2 issue(s): ArgumentResolutionError (1), InvalidScopeDependencyError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.resolution.ArgumentResolutionError: Argument missing of type <class 'myapp.Missing'> cannot be resolved. Trying to build dependency <class 'myapp.NeedsMissing'>.
    | Did you mean:
    |   - NeedsMissing (similar name, scope=APP)
    | See: https://modern-di.modern-python.org/troubleshooting/argument-resolution-error/
    +---------------- 2 ----------------
    | modern_di.exceptions.registration.InvalidScopeDependencyError: Provider at a deeper scope reached through this chain:
    |   APP      Shallow
    |   REQUEST  └─> Deep
    |   caused by: Shallow (scope APP) declares parameter 'deep' typed as a provider of Deep at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
    | See: https://modern-di.modern-python.org/troubleshooting/scope-chain/
    +------------------------------------
```

`logger.exception` prints the same tree. A plain `print(exc)` or `str(exc)` gives only the summary
line.

## Cause

The provider graph has one or more problems: a circular dependency, a provider depending on a
deeper-scoped one, a creator parameter with no way to be resolved, or an alias whose source type has
no registered provider. `validate()` collects every
issue across the whole graph in one pass rather than stopping at the first one, so `.exceptions`
may hold several distinct exception types at once.

## Fix

Inspect `.exceptions` to see every underlying issue, or read the traceback. Each issue is one of `CircularDependencyError`, `InvalidScopeDependencyError`, `ScopeEnumMismatchError`,
`ArgumentResolutionError`, or `AliasSourceNotRegisteredError` today. Fix each one; their own pages cover the specific cause and
remedy:

<!-- skip: next "fragment" -->

```python
try:
    container.validate()
except exceptions.ValidationFailedError as exc:
    for error in exc.exceptions:
        print(type(error).__name__, error)
```

To handle one kind of issue and let the rest propagate, use `except*`:

<!-- skip: next "fragment" -->

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
