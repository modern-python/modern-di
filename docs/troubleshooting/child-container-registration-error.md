# ChildContainerRegistrationError

## Symptom

Raised from `Container.add_providers()` on a child container. It names the child container's scope.

## Cause

Providers were registered on a child container rather than the root. The providers registry is
shared tree-wide (every container in the chain points at the same registry), so registering from a
child would silently mutate every container in the tree, so the call is disallowed.

## Fix

Register on the root container instead, either with `groups=` when you build it or with
`add_providers()` later:

<!-- skip: next "fragment" -->

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup])
request_container = app_container.build_child_container(scope=Scope.REQUEST)

# Broken
request_container.add_providers(late_provider)  # raises ChildContainerRegistrationError

# Works
app_container.add_providers(late_provider)
```

If you only have a reference to the child container at the call site, keep a reference to the root
container around (e.g. store it at app startup) instead of walking up via `parent_container`.

## See also

- [Container: registering providers after construction](../providers/container.md#registering-providers-after-construction).
