# InvalidScopeTypeError

## Symptom

Raised when constructing a `Container`, when calling `build_child_container()`, or when defining a `Group` subclass with a `scope=` class kwarg, naming the value that was passed as `scope=` and its type.

## Cause

`scope=` must be an `enum.IntEnum` member. This fires in three contexts:

1. When passed to the `Container` constructor, with a plain `int`, a string, a regular `enum.Enum` (not `IntEnum`), or any other non-`IntEnum` value.
2. When passed to `build_child_container()`; the same validation applies.
3. When passed to a `Group` subclass as a class kwarg; the same validation applies.

Example invalid uses: `Container(scope=1)`, `Container(scope="APP")`, `container.build_child_container(scope=3)`, `class MyGroup(Group, scope=1)`, `class MyGroup(Group, scope="REQUEST")`.

## Fix

Use the built-in `Scope` enum, or your own `IntEnum` subclass:

<!-- skip: next "raises InvalidScopeTypeError on purpose" -->

```python
from modern_di import Container, Scope

# Broken
container = Container(scope=1)                 # raises InvalidScopeTypeError
container = Container(scope="APP")              # raises InvalidScopeTypeError

# Works
container = Container(scope=Scope.APP)
```

If you need scopes beyond the five built-in ones, define your own `enum.IntEnum` whose members'
values are ordered the way you want the hierarchy to resolve, and use that instead of `Scope`.

## See also

- [Scopes](../providers/scopes.md) explains the `IntEnum` hierarchy and why membership is required.
