# InvalidChildScopeError

**Symptom**

Raised from `Container(...)` or `build_child_container(scope=...)`, naming the parent scope, the
requested child scope, and the list of scopes that would have been accepted.

**Cause**

A child's scope must be strictly deeper (a higher `IntEnum` value) than the parent's. Passing an
explicit `scope=` that is equal to the parent's (e.g. `Scope.SESSION` from a `SESSION` parent) or
shallower (e.g. `Scope.APP` from a `SESSION` parent) raises this error.

**Fix**

Pass a scope whose value is strictly greater than the parent's:

```python
from modern_di import Scope

app_container = Container(scope=Scope.APP, groups=[MyGroup])

# Wrong: SESSION is not deeper than SESSION
mid = app_container.build_child_container(scope=Scope.SESSION)
bad = mid.build_child_container(scope=Scope.SESSION)  # raises InvalidChildScopeError

# Right
good = mid.build_child_container(scope=Scope.REQUEST)
```

**Escape hatches**

Omit `scope=` entirely — `build_child_container()` derives the next deeper scope automatically, so
this error can only occur when you explicitly pin a scope value. Inspect `.allowed_scopes` on the
caught exception for the exact list of valid choices at that point in the tree.

## See also

- [Scopes](../providers/scopes.md#the-scope-dependency-rule) — the scope hierarchy and ordering rule.
