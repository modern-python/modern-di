# ChildContainerRegistrationError

**Symptom**

Raised from `Container.add_providers()`, naming the scope of the child container it was called on.

**Cause**

`add_providers()` was called on a child container rather than the root. The providers registry is
shared tree-wide (every container in the chain points at the same registry), so registering from a
child would silently mutate every container in the tree — this is disallowed rather than done
implicitly.

**Fix**

Call `add_providers()` on the root container instead:

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup])
app_container.open()
request_container = app_container.build_child_container(scope=Scope.REQUEST)

# Wrong
request_container.add_providers(late_provider)  # raises ChildContainerRegistrationError

# Right
app_container.add_providers(late_provider)
```

If you only have a reference to the child container at the call site, keep a reference to the root
container around (e.g. store it at app startup) instead of walking up via `parent_container`.

## See also

- [Container: registering providers after construction](../providers/container.md#registering-providers-after-construction).
