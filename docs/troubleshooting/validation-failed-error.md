# ValidationFailedError

## Symptom

Raised by `Container.validate()`. Its message is one line naming each kind of issue with its count,
followed by a link to this page. It is an `ExceptionGroup`, so a traceback shows each issue in full
below that line:

```text
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.container.ValidationFailedError: Container.validate() found 2 issue(s): ArgumentResolutionError (1), InvalidScopeDependencyError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.resolution.ArgumentResolutionError: Argument missing of type <class 'myapp.providers.Missing'> cannot be resolved. Trying to build dependency <class 'myapp.providers.NeedsMissing'>.
    | Did you mean:
    |   - NeedsMissing (similar name, scope=APP)
    | See: https://modern-di.modern-python.org/troubleshooting/argument-resolution-error/
    +---------------- 2 ----------------
    | modern_di.exceptions.registration.InvalidScopeDependencyError: Provider at a deeper scope reached through this chain:
    |   APP      Shallow (myapp.providers:15)
    |   REQUEST  └─> Deep (myapp.providers:12)
    |   caused by: Shallow (scope APP) declares parameter 'deep' typed as a provider of Deep at deeper scope REQUEST. A provider cannot depend on a deeper-scoped provider.
    | See: https://modern-di.modern-python.org/troubleshooting/scope-chain/
    +------------------------------------
```

`logger.exception` prints the same tree. A plain `print(exc)` or `str(exc)` gives only the summary
line and the `See:` line.

## Cause

The provider graph has one or more problems. `validate()` walks the whole graph in one pass and
collects every issue, so `.exceptions` may hold several kinds at once. Each entry is one of these:

- [`CircularDependencyError`](circular-dependency.md) — a cycle in the graph.
- [`InvalidScopeDependencyError`](scope-chain.md) — a provider that depends on a deeper-scoped one.
- [`ScopeEnumMismatchError`](scope-enum-mismatch-error.md) — a dependency at a same-valued scope of
  another enum.
- [`ArgumentResolutionError`](argument-resolution-error.md) — a creator parameter that nothing can
  resolve.
- [`AliasSourceNotRegisteredError`](alias-source-not-registered-error.md) — an alias whose source
  type has no provider.

## Fix

Read the traceback or inspect `.exceptions`, then fix each issue as its own page describes:

<!-- invisible-code-block: python
from modern_di import Container, Group, exceptions, providers


class Missing: ...


class NeedsMissing:
    def __init__(self, missing: Missing) -> None:
        self.missing = missing


class Dependencies(Group):
    needs_missing = providers.Factory(NeedsMissing)


container = Container(groups=[Dependencies])
-->

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

Nothing validates the graph for you, not even construction, `open()` or `resolve()`. Call
`validate()` at startup, before the first real request, so graph bugs fail there in one error.

## See also

- [Lifecycle: validation](../providers/lifecycle.md#validation) — when to call `validate()` and what
  it checks.
