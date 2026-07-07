# GroupInstantiationError

**Symptom**

Raised naming the `Group` subclass someone tried to instantiate, saying it cannot be created as an
object.

**Cause**

A `Group` subclass was called like a constructor (`MyGroup()`). Groups are namespaces for declaring
providers as class attributes — they're never meant to be instantiated, only passed by class
reference to `Container(groups=[MyGroup])` or read via `MyGroup.some_provider`.

**Fix**

Use the class itself, not an instance:

```python
class Dependencies(Group):
    service = providers.Factory(scope=Scope.APP, creator=Service)


# Wrong
deps = Dependencies()             # raises GroupInstantiationError

# Right
container = Container(groups=[Dependencies])
service = container.resolve_provider(Dependencies.service)
```

This usually happens from a habit carried over from frameworks where a container/module *is*
instantiated, or from accidentally writing `Dependencies()` instead of `Dependencies` in a type
annotation or default value.

## See also

- [Multi-Group organization](../recipes/multi-group.md) — organizing providers across several `Group` classes.
