# ArgumentResolutionError

## Symptom

Raised naming a creator's parameter and the type it's annotated with, saying the argument couldn't be
resolved while building a given dependency, often rendered as a dependency-chain trace with a
`caused by:` line naming the specific parameter.

## Cause

A creator parameter has no registered provider for its annotated type, no default value, and no
matching `kwargs` entry, so `modern-di` has nothing to inject. This also covers an unannotated
parameter with none of those escape routes. A required `ContextProvider`-backed parameter whose
context value is unset raises [`ContextValueNotSetError`](context-not-set.md) instead.

## Fix

Pick whichever applies: register a provider for the missing type, give the parameter a default, or
pass it explicitly via `kwargs`:

<!-- invisible-code-block: python
from modern_di import Group, Scope, providers


class Clock: ...


class SystemClock(Clock): ...


class Service:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
-->

```python
class Dependencies(Group):
    # missing: no provider for `Clock` anywhere
    service = providers.Factory(Service, scope=Scope.APP)  # Service(clock: Clock)

    # fix option 1: register a provider
    clock = providers.Factory(SystemClock, scope=Scope.APP, bound_type=Clock)

    # fix option 2: pass explicitly
    service2 = providers.Factory(Service, scope=Scope.APP, kwargs={"clock": clock})
```

If the missing type is one a framework
integration provides at runtime (`fastapi.Request`, `taskiq.TaskiqMessage`, …), its
`ContextProvider` is registered by `setup_di()`, so a `container.validate()` call made
*before* `setup_di()` runs sees no provider for it yet and raises. Call `validate()` after
`setup_di()`, when the provider is registered. A factory that must also resolve outside a
request can take `request: fastapi.Request | None = None`: once `setup_di()` has registered the
provider, the parameter gets the request inside one and `None` outside. See
[Framework context objects](../providers/context.md#framework-context-objects) and
[Optional parameters](../providers/context.md#optional-parameters).

Check `.suggestions` on the caught exception for a "did you mean" hint when a similarly-named type is
registered instead.

## See also

- [No provider registered for type](missing-provider.md) describes the direct-resolve form of this same gap.
- [Factories](../providers/factories.md#creator) explains how parameters are parsed and wired.
