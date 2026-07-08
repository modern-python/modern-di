# ArgumentResolutionError

**Symptom**

Raised naming a creator's parameter and the type it's annotated with, saying the argument couldn't be
resolved while building a given dependency — often rendered as a dependency-chain trace with a
`caused by:` line naming the specific parameter.

**Cause**

A creator parameter has no registered provider for its annotated type, no default value, and no
matching `kwargs` entry — so `modern-di` has nothing to inject. This also covers an unannotated
parameter with none of those escape routes, and a `ContextProvider`-backed parameter whose context
value is unset and required (not optional, no default).

**Fix**

Pick whichever applies: register a provider for the missing type, give the parameter a default, or
pass it explicitly via `kwargs`:

```python
class Dependencies(Group):
    # missing: no provider for `Clock` anywhere
    service = providers.Factory(Service, scope=Scope.APP)  # Service(clock: Clock)

    # fix option 1: register a provider
    clock = providers.Factory(SystemClock, scope=Scope.APP, bound_type=Clock)

    # fix option 2: pass explicitly
    service2 = providers.Factory(Service, scope=Scope.APP, kwargs={"clock": clock})
```

Check `.suggestions` on the caught exception for a "did you mean" hint when a similarly-named type is
registered instead.

## See also

- [No provider registered for type](missing-provider.md) — the direct-resolve form of this same gap.
- [Factories](../providers/factories.md#creator) — how parameters are parsed and wired.
