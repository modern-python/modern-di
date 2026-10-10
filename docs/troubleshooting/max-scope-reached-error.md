# MaxScopeReachedError

## Symptom

`build_child_container()` called without `scope=` raises it when the parent is at the last member of
its scope enum:

```text
modern_di.exceptions.container.MaxScopeReachedError: Max scope of STEP is reached. To go deeper, build a child container with a custom IntEnum scope whose value is higher.
See: https://modern-di.modern-python.org/troubleshooting/max-scope-reached-error/
```

`.parent_scope` holds the parent's scope.

## Cause

Without `scope=`, `build_child_container()` picks the smallest member of the parent's own enum that
is greater than the parent's scope. It never looks at another enum. The built-in `Scope` enum ends at
`STEP`, so a `STEP` container has no next member to advance to.

## Fix

First check whether the provider needs a scope deeper than `STEP`, or whether it belongs at an
existing scope. If it does need one, define an `IntEnum` with a member deeper than `STEP` and pass it
explicitly:

<!-- invisible-code-block: python
from modern_di import Container, Scope

step_container = Container(scope=Scope.STEP)
-->

```python
import enum

from modern_di import Scope


class MyScope(enum.IntEnum):
    SUBSTEP = Scope.STEP + 1


substep_container = step_container.build_child_container(scope=MyScope.SUBSTEP)
```

A call without `scope=` on `substep_container` raises this error again, because `SUBSTEP` is the last
member of `MyScope`. Pass the scope explicitly at each level below `STEP`, or define one `IntEnum`
that holds every level you use, from the root down, and use it in place of `Scope`. Then every child
can derive its scope:

```python
class AppScope(enum.IntEnum):
    APP = 1
    SESSION = 2
    REQUEST = 3
    ACTION = 4
    STEP = 5
    SUBSTEP = 6


container = Container(scope=AppScope.APP)
for _ in range(5):
    container = container.build_child_container()

print(container.scope.name)  # SUBSTEP
```

Every provider then has to be declared at an `AppScope` member. A provider at `Scope.APP` does not
resolve in an `AppScope.APP` container: members of different enums are different scopes even when
their values match, and resolving raises [`ScopeSkippedError`](scope-skipped-error.md).

## See also

- [Scopes: custom scopes](../providers/scopes.md#custom-scopes) — extending the hierarchy with your
  own `IntEnum`.
- [InvalidChildScopeError](invalid-child-scope-error.md) — the error for an explicit `scope=` that is
  not deeper than the parent's.
