# InvalidScopeTypeError

**Symptom**

Raised from the `Container` constructor, naming the value that was passed as `scope=` and its type.

**Cause**

`scope=` must be an `enum.IntEnum` member. This fires when a plain `int`, a string, a regular
`enum.Enum` (not `IntEnum`), or any other non-`IntEnum` value is passed instead.

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
