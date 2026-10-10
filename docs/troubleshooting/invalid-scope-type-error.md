# InvalidScopeTypeError

## Symptom

Raised when a value passed as `scope=` is not an `enum.IntEnum` member. The message shows the value
and its type:

```text
modern_di.exceptions.container.InvalidScopeTypeError: Scope must be an enum.IntEnum member; got 1 (int).
See: https://modern-di.modern-python.org/troubleshooting/invalid-scope-type-error/
```

`.scope_value` holds the value that was passed.

## Cause

`Container(scope=...)`, `build_child_container(scope=...)` and a group declared as
`class MyGroup(Group, scope=...)` all check the value, and each rejects an `int`, a `str`, a member of
a plain `enum.Enum`, and a member of an `enum.IntFlag`.

## Fix

Pass a member of `Scope` or of your own `IntEnum`:

<!-- raises: InvalidScopeTypeError -->

```python
from modern_di import Container, Scope

# Broken
container = Container(scope=1)
```

```python
# Works
container = Container(scope=Scope.APP)
```

When the scope comes from configuration as a number or a name, convert it to a member first:

```python
assert Scope(3) is Scope.REQUEST
assert Scope["REQUEST"] is Scope.REQUEST
```

For scopes beyond the five built-in ones, define your own `enum.IntEnum` and order its values the
way the hierarchy should nest.

## See also

- [Scopes: custom scopes](../providers/scopes.md#custom-scopes) — using your own `IntEnum` as a
  scope.
