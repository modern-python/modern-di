# MaxScopeReachedError

**Symptom**

Raised from `build_child_container()` called with no explicit `scope=` argument, naming the parent
scope that has no deeper scope to advance to.

**Cause**

`build_child_container()` without an explicit `scope=` auto-derives the next deeper scope by picking
the smallest enum member greater than the parent's. The built-in `Scope` enum ends at `STEP`; calling
`build_child_container()` on a `STEP`-scope container has nowhere further to go.

**Fix**

Define a custom `IntEnum` scope with a member deeper than `STEP` and build the child with that scope
explicitly:

```python
import enum

from modern_di import Scope


class ExtendedScope(enum.IntEnum):
    APP = Scope.APP
    SESSION = Scope.SESSION
    REQUEST = Scope.REQUEST
    ACTION = Scope.ACTION
    STEP = Scope.STEP
    SUBSTEP = 6


step_container = Container(scope=ExtendedScope.STEP, parent_container=action_container)
step_container.open()
sub_container = step_container.build_child_container(scope=ExtendedScope.SUBSTEP)
```

Root containers rarely need this — reconsider whether the provider actually needs a scope deeper than
`STEP`, or whether it belongs at an existing shallower scope instead.

## See also

- [Scopes](../providers/scopes.md) — the built-in hierarchy and how to extend it with a custom `IntEnum`.
