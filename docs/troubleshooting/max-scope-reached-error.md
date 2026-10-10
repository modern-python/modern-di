# MaxScopeReachedError

## Symptom

Raised from `build_child_container()` called with no explicit `scope=` argument, naming the parent
scope that has no deeper scope to advance to.

## Cause

`build_child_container()` without an explicit `scope=` auto-derives the next deeper scope by picking
the smallest enum member greater than the parent's. The built-in `Scope` enum ends at `STEP`; calling
`build_child_container()` on a `STEP`-scope container has nowhere further to go.

## Fix

Define an `IntEnum` with a member deeper than `STEP` and build the child with that scope explicitly:

<!-- skip: next "fragment" -->

```python
import enum

from modern_di import Scope


class MyScope(enum.IntEnum):
    SUBSTEP = Scope.STEP + 1


sub_container = step_container.build_child_container(scope=MyScope.SUBSTEP)
```

Root containers rarely need this. Reconsider whether the provider actually needs a scope deeper than
`STEP`, or whether it belongs at an existing shallower scope instead.

## See also

- [Scopes](../providers/scopes.md) explains the built-in hierarchy and how to extend it with a custom `IntEnum`.
