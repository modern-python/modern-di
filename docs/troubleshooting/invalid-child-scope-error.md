# InvalidChildScopeError

## Symptom

`build_child_container(scope=...)` raises it when the scope you pass is not deeper than the parent's:

```text
modern_di.exceptions.container.InvalidChildScopeError: Scope of child container cannot be SESSION if parent scope is SESSION (child scope value must be strictly greater than parent scope value). Possible scopes are ['REQUEST', 'ACTION', 'STEP'].
See: https://modern-di.modern-python.org/troubleshooting/invalid-child-scope-error/
```

`.parent_scope` and `.child_scope` hold the two scopes, and `.allowed_scopes` holds the members
listed after `Possible scopes are`. The `Container(...)` constructor never raises this error, because
a root container can start at any scope.

## Cause

A child's scope must have a strictly higher integer value than its parent's. A child at the same
scope (`Scope.SESSION` under a `SESSION` parent) or a shallower one (`Scope.APP` under a `SESSION`
parent) raises.

The check compares integer values, so a member of another `IntEnum` is accepted when its value is
higher. The message and `.allowed_scopes` list only the deeper members of the parent's own enum,
though. Under a `STEP` parent, or a parent at the last member of a custom enum, the message says
`Possible scopes are [].` even though a higher-valued member of another enum would be accepted.

## Fix

Pass a scope deeper than the parent's:

<!-- invisible-code-block: python
from modern_di import Container, Scope

app_container = Container(scope=Scope.APP)
session_container = app_container.build_child_container(scope=Scope.SESSION)
-->

<!-- raises: InvalidChildScopeError -->

```python
# Broken: SESSION is not deeper than SESSION
session_container.build_child_container(scope=Scope.SESSION)
```

```python
# Works
request_container = session_container.build_child_container(scope=Scope.REQUEST)
```

You can also omit `scope=`. `build_child_container()` then takes the next deeper member of the
parent's enum and never raises this error. When the enum has no deeper member it raises
[`MaxScopeReachedError`](max-scope-reached-error.md) instead.

To go deeper than the parent's enum reaches, pass a member of your own `IntEnum` with a higher value:

```python
import enum


class MyScope(enum.IntEnum):
    SUBSTEP = Scope.STEP + 1


step_container = Container(scope=Scope.STEP)
substep_container = step_container.build_child_container(scope=MyScope.SUBSTEP)
```

## See also

- [Scopes: custom scopes](../providers/scopes.md#custom-scopes) — how members of different enums mix
  in one container tree.
- [MaxScopeReachedError](max-scope-reached-error.md) — the error from `build_child_container()`
  without `scope=` at the last member of an enum.
