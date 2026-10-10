# ChildContainerRegistrationError

## Symptom

`Container.add_providers()` raises it when called on a child container:

```text
modern_di.exceptions.registration.ChildContainerRegistrationError: Providers can only be registered on a root container: the providers registry is shared tree-wide, so registering on a child container (scope REQUEST) would mutate every container in the tree. Pass groups= to the root Container or call add_providers on it instead.
See: https://modern-di.modern-python.org/troubleshooting/child-container-registration-error/
```

`.container_scope` holds the child container's scope.

## Cause

Every container in a tree shares one providers registry, so a registration on a child would change
what every other container in the tree resolves. `add_providers()` accepts calls only on a root.

## Fix

Register on the root container, either with `groups=` when you build it or with `add_providers()`
afterwards:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Settings: ...


class Mailer: ...


class MyGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP)


late_provider = providers.Factory(Mailer, scope=Scope.APP)

app_container = Container(scope=Scope.APP, groups=[MyGroup])
request_container = app_container.build_child_container(scope=Scope.REQUEST)
-->

<!-- raises: ChildContainerRegistrationError -->

```python
# Broken
request_container.add_providers(late_provider)
```

```python
# Works
app_container.add_providers(late_provider)
```

Any root works, whatever its scope. Register at startup, because `add_providers()` is not
coordinated with resolves running at the same time on other threads.

## See also

- [Container: registering providers after construction](../providers/container.md#registering-providers-after-construction).
