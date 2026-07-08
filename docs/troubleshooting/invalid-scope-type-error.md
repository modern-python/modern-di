# InvalidScopeTypeError

**Symptom**

Raised when constructing a `Container` or when defining a `Group` subclass with a `scope=` class kwarg, naming the value that was passed as `scope=` and its type.

**Cause**

`scope=` must be an `enum.IntEnum` member. This fires in two contexts:

1. When passed to the `Container` constructor — when a plain `int`, a string, a regular `enum.Enum` (not `IntEnum`), or any other non-`IntEnum` value is used.
2. When passed to a `Group` subclass as a class kwarg — same validation applies.

Example invalid uses: `Container(scope=1)`, `Container(scope="APP")`, `class MyGroup(Group, scope=1)`, `class MyGroup(Group, scope="REQUEST")`.

**Fix**

Use the built-in `Scope` enum, or your own `IntEnum` subclass:

```python
from modern_di import Container, Scope

# Wrong
container = Container(scope=1)                 # raises InvalidScopeTypeError
container = Container(scope="APP")              # raises InvalidScopeTypeError

# Right
container = Container(scope=Scope.APP)
```

If you need scopes beyond the five built-in ones, define your own `enum.IntEnum` whose members'
values are ordered the way you want the hierarchy to resolve, and use that instead of `Scope`.

## See also

- [Scopes](../providers/scopes.md) — the `IntEnum` hierarchy and why membership is required.
