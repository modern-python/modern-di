# Migration Guide: Upgrading to modern-di 3.x

This document describes the changes required to migrate from modern-di 2.x to modern-di 3.0.

## Overview

modern-di 3.0 flips five switches from warn-then-continue to raise/validate-by-default. Every one
of them already has a 2.x signal — a warning that fires today wherever the 3.0 behavior would
differ. If your 2.x test suite is green with the [readiness recipe](#readiness-recipe-escalating-warnings-to-errors-with-filterwarnings) below
escalating those warnings to errors, the upgrade to 3.0 is a no-op for you.

## The five switches

| 3.0 change | 2.x signal |
|---|---|
| Reusing a closed container raises `ContainerClosedError` | `ContainerClosedWarning` |
| `Alias(scope=)` parameter removed | `DeprecationWarning` |
| `Factory(cache_settings=)` removed | `DeprecationWarning` |
| `validate()` runs by default at root construction | `UnvalidatedContainerWarning` |
| Direct resolve of an unset `ContextProvider` raises `ContextValueNotSetError` | `ContextValueNoneWarning` |

## Key Changes

### 1. Closed containers raise instead of self-healing

In 2.x, resolving from (or building a child of) a closed container emits `ContainerClosedWarning`
and transparently reopens the container so the call still succeeds. In 3.0 the same call raises
`ContainerClosedError` instead.

**Before (2.x):**
```python
container = Container(scope=Scope.APP, groups=[MyGroup], validate=True)
container.close_sync()

# ContainerClosedWarning: Container (scope APP) is closed; resolving from it or
# building a child is deprecated and will raise ContainerClosedError in modern-di
# 3.0. Re-enter the container with `with`/`async with`, or call `open()`, before
# reusing it.
service = container.resolve(MyService)  # succeeds — container self-reopens
```

**After (3.0):**
```python
container = Container(scope=Scope.APP, groups=[MyGroup], validate=True)
container.close_sync()

service = container.resolve(MyService)  # raises ContainerClosedError
```

Re-enter the container with `with`/`async with`, or call `container.open()`, before reusing it.

### 2. `Alias(scope=)` parameter removed

`Alias`'s effective scope has always been derived from its source provider; the `scope` argument
never affected resolution. In 2.x, passing it emits a `DeprecationWarning`; in 3.0 the parameter is
gone.

**Before (2.x):**
```python
from modern_di import Scope, providers

# DeprecationWarning: The `scope` parameter of Alias is deprecated and ignored:
# an alias's effective scope is derived from its source. It will be removed in
# a future release.
alias = providers.Alias(source_type=DatabaseProtocol, scope=Scope.APP)
```

**After (3.0):**
```python
from modern_di import providers

alias = providers.Alias(source_type=DatabaseProtocol)
```

### 3. `Factory(cache_settings=)` removed

`cache_settings=` was the pre-`cache=` spelling for tuning a `Factory`'s cache. In 2.x it still
works but warns; in 3.0 only `cache=` is accepted.

**Before (2.x):**
```python
# DeprecationWarning: `cache_settings=` is deprecated; use `cache=` (pass
# cache=True for defaults, or cache=CacheSettings(...) to tune). It will be
# removed in a future release.
factory = providers.Factory(
    scope=Scope.REQUEST,
    creator=create_resource,
    cache_settings=providers.CacheSettings(finalizer=lambda resource: resource.close()),
)
```

**After (3.0):**
```python
factory = providers.Factory(
    scope=Scope.REQUEST,
    creator=create_resource,
    cache=providers.CacheSettings(finalizer=lambda resource: resource.close()),
)
```

### 4. `validate()` runs by default at root construction

In 2.x, leaving the `Container` constructor's `validate` argument unset skips validation (as
before) but emits `UnvalidatedContainerWarning`. In 3.0, leaving it unset runs `validate()`
automatically, so an invalid graph raises `ValidationFailedError` at construction time instead of
failing lazily on first resolve.

**Before (2.x):**
```python
# UnvalidatedContainerWarning: This root container was created without an
# explicit `validate` argument. modern-di 3.0 runs validate() at root
# construction by default. Pass validate=True to adopt the 3.0 behavior now,
# or validate=False to keep validation off.
container = Container(scope=Scope.APP, groups=[MyGroup])
```

**After (3.0):**
```python
# validate() runs automatically; raises ValidationFailedError if the graph
# has cycles or scope-ordering problems.
container = Container(scope=Scope.APP, groups=[MyGroup])

# Opt out of validation — this spelling works identically before and after 3.0.
container = Container(scope=Scope.APP, groups=[MyGroup], validate=False)
```

Child containers (built via `build_child_container`) never validate and never warn, in either
version — this switch only affects root construction.

### 5. Direct resolve of an unset `ContextProvider` raises

In 2.x, resolving a type backed by a `ContextProvider` with no value set emits
`ContextValueNoneWarning` and returns `None`. In 3.0 the same call raises
`ContextValueNotSetError`. This only affects a *direct* resolve of the context type; a `Factory`
parameter backed by the same `ContextProvider` continues to follow its own
default/nullable/required disposition, unchanged.

**Before (2.x):**
```python
# ContextValueNoneWarning: No context value is set for <class '...'> (scope
# APP); returning None. modern-di 3.0 raises ContextValueNotSetError here.
# Pass context={...} to the container or call set_context().
value = container.resolve(SomeContextType)  # None
```

**After (3.0):**
```python
value = container.resolve(SomeContextType)  # raises ContextValueNotSetError
```

Pass `context={SomeContextType: value}` to the container (or its ancestor at the
`ContextProvider`'s scope), or call `container.set_context(SomeContextType, value)`, before
resolving.

## Readiness recipe: escalating warnings to errors with `filterwarnings`

This is the one place in the docs that lists the full `filterwarnings` escalation recipe; every
other page that mentions escalating a specific warning links back here.

`ContainerClosedWarning` and `ContextValueNoneWarning` subclass `DeprecationWarning`;
`UnvalidatedContainerWarning` subclasses `FutureWarning`; the `Alias(scope=)` and
`Factory(cache_settings=)` warnings are plain `DeprecationWarning` (they have no dedicated
subclass). Escalating both categories to errors therefore turns all five signals into failures a
green test suite would catch:

```python
import warnings

warnings.filterwarnings("error", category=DeprecationWarning)
warnings.filterwarnings("error", category=FutureWarning)
```

plus the pytest variant:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "error::DeprecationWarning",
    "error::FutureWarning",
]
```

!!! warning "Don't add a `module=` filter here"
    It's tempting to scope the filter to modern-di with
    `module=r"modern_di(\..*)?"`, but that argument matches the module of the *warned-from*
    frame at the warning's `stacklevel`, not the module that owns the warning class. Three of the
    five signals (`UnvalidatedContainerWarning`, and the `Alias(scope=)` / `Factory(cache_settings=)`
    warnings) are raised directly inside the constructor call with `stacklevel=2`, which attributes
    them to *your* calling module — not `modern_di` — so a `module=r"modern_di(\..*)?"` filter
    silently fails to escalate them. The other two (`ContainerClosedWarning`,
    `ContextValueNoneWarning`) fire deep inside a resolve call, where the `stacklevel=2` frame
    happens to still be inside `modern_di`, so they *would* match — the inconsistency is exactly
    why `module=` isn't part of the recipe above.

If the broad category filter is too wide for your process (e.g. another dependency's
`DeprecationWarning`s should stay warnings), escalate the three dedicated subclasses individually
instead — this covers switches 1, 4, and 5 precisely, but not 2 and 3, since those two have no
dedicated class in 2.x:

```python
from modern_di import exceptions

warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)
warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)
warnings.filterwarnings("error", category=exceptions.ContextValueNoneWarning)
```

## Deprecation policy

Every breaking change in modern-di is warned for at least one minor release cycle before it flips
or is removed at the next major. If you're on a 2.x release and see none of the five warnings
above under the readiness recipe, upgrading to 3.0 requires no code changes on your part.
