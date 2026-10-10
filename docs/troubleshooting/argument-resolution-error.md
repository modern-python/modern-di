# ArgumentResolutionError

## Symptom

```
modern_di.exceptions.resolution.ArgumentResolutionError: Cannot resolve dependency chain:
  APP  Service (myapp.clock:10)
  caused by: Argument clock of type <class 'myapp.clock.Clock'> cannot be resolved. Trying to build dependency <class 'myapp.clock.Service'>.
Did you mean:
  - SystemClock (registered subclass, scope=APP)
See: https://modern-di.modern-python.org/troubleshooting/argument-resolution-error/
```

The chain shows the provider being built, and the `caused by:` line names the parameter and its
annotation. The `Did you mean:` block appears only when a registered type looks like the one
requested: a registered subclass, a registered base class, or a type with a similar name. Two other
forms of the `caused by:` line exist:

- `Argument dep of type A | B cannot be resolved.` for a union parameter where no member has a provider.
- `Argument x has no usable type annotation, so it cannot be resolved by type. Pass it via the kwargs parameter or add a type annotation.` for an unannotated parameter.

`container.validate()` reports the same error inside
[`ValidationFailedError`](validation-failed-error.md). The exception carries `.parameter_name`,
`.parameter_type`, `.member_types` (the union members, for a union parameter), `.bound_type`,
`.creator` and `.suggestions`.

## Cause

A creator parameter has nothing to inject: no provider is registered for its annotated type, it has
no default, it is not nullable (`X | None`), and `kwargs` has no entry for it. The usual reasons:

- The type has no provider, or its group was not passed to `Container(groups=[...])`.
- The provider exists under another type. A `Factory(SystemClock)` registers under `SystemClock`, so a
  parameter typed `Clock` does not find it. This is the case the `registered subclass` hint points at.
- The parameter has no type annotation.
- The parameter is a union. `modern-di` injects the first member, in the order the union lists them,
  that has a provider, and raises this error when none has one.

A required parameter backed by a `ContextProvider` whose value is unset raises
[`ContextValueNotSetError`](context-not-set.md) instead.

## Fix

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Clock: ...


class SystemClock(Clock): ...


class Service:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
-->

<!-- raises: ArgumentResolutionError -->

```python
# Broken:
class Dependencies(Group):
    system_clock = providers.Factory(SystemClock, scope=Scope.APP)
    service = providers.Factory(Service, scope=Scope.APP)


Container(groups=[Dependencies]).resolve(Service)
```

Register the provider under the type the parameter asks for:

```python
# Works:
class Dependencies(Group):
    system_clock = providers.Factory(SystemClock, scope=Scope.APP, bound_type=Clock)
    service = providers.Factory(Service, scope=Scope.APP)


assert isinstance(Container(groups=[Dependencies]).resolve(Service).clock, SystemClock)
```

Or pass the provider explicitly through `kwargs`. With `bound_type=None` the clock is reachable only
by reference:

```python
# Works:
class Dependencies(Group):
    system_clock = providers.Factory(SystemClock, scope=Scope.APP, bound_type=None)
    service = providers.Factory(Service, scope=Scope.APP, kwargs={"clock": system_clock})


assert isinstance(Container(groups=[Dependencies]).resolve(Service).clock, SystemClock)
```

Giving the parameter a default, or annotating it as `Clock | None`, also stops the error; the creator
then gets the default or `None`.

### Framework types

A type such as `fastapi.Request` or `taskiq.TaskiqMessage` gets its `ContextProvider` from the
integration's `setup_di()`. A `container.validate()` call made before `setup_di()` sees no provider
for it and reports this error, so call `validate()` after `setup_di()`. A factory that must also
resolve outside a request can take `request: fastapi.Request | None = None`: it gets the request
inside one and `None` outside. See
[Framework context objects](../providers/context.md#framework-context-objects) and
[Optional parameters](../providers/context.md#optional-parameters).

## See also

- [ProviderNotRegisteredError](missing-provider.md): the same gap, hit by a direct `resolve`.
- [Factories: creator](../providers/factories.md#creator): how creator parameters are parsed and wired.
- [Factories: union type parameters](../providers/factories.md#union-type-parameters): which union member is injected.
- [Framework context objects](../providers/context.md#framework-context-objects): the providers integrations register.
