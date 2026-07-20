# Migration Guide: Upgrading to modern-di 3.x

This document describes the changes required to migrate from modern-di 2.x to modern-di 3.0.

## Overview

modern-di 3.0 flips five switches from warn-then-continue to raise/validate-by-default, and adds
one more that has no 2.x precedent to warn from. Each of the five already has a 2.x signal — a
warning that fires today wherever the 3.0 behavior would differ. If your 2.x test suite is green
with the [readiness recipe](#readiness-recipe-escalating-warnings-to-errors-with-filterwarnings)
below escalating those five warnings to errors, **those five switches** are a no-op for you.

3.0 **additionally** requires a container to be opened (`with`/`async with`/`open()`) before it can
`resolve` or `build_child_container` — switch 6 below — and changes `validate`'s constructor
signature from `bool | None` to a plain `bool`. Neither has a 2.x warning to escalate: 2.x has no
"unopened" state to signal on, and an explicit `validate=True` in 2.x validates eagerly at
construction, a timing 3.0 changes without ever warning about it. These are genuine hard breaks —
a green suite under the recipe does not, by itself, get you past them. See
[switch 4](#4-validate-runs-at-container-entry-on-by-default) and
[switch 6](#6-a-container-must-be-opened-before-use) below.

## The six switches

| 3.0 change | 2.x signal |
|---|---|
| Reusing a closed container raises `ContainerClosedError` | `ContainerClosedWarning` |
| `Alias(scope=)` parameter removed | `DeprecationWarning` |
| `Factory(cache_settings=)` removed | `DeprecationWarning` |
| `validate` defaults to `True` and runs at container entry (`open()`/`with`) | `UnvalidatedContainerWarning` — covers the *unset* case only; see below |
| Direct resolve of an unset `ContextProvider` raises `ContextValueNotSetError` | `ContextValueNoneWarning` |
| A container must be opened before `resolve`/`build_child_container` | **none** — inherent hard break, no 2.x state to warn from |

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
with container:
    service = container.resolve(MyService)  # works — container is open inside the block

# the `with` block closed the container on exit
service = container.resolve(MyService)  # raises ContainerClosedError — reused after close
```

Re-enter the container with `with`/`async with`, or call `container.open()`, before reusing it.

This is one half of a single rule: **a container must be open to be used.** This switch is the
*closed-after-use* half (a container that was open, then closed); [switch 6](#6-a-container-must-be-opened-before-use)
below is the *never-opened* half (a fresh container that was never entered at all). Both raise the
same `ContainerClosedError`, and both are fixed the same way — enter the container with
`with`/`async with`, or call `open()`, before resolving or building children.

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
alias = providers.Alias(DatabaseProtocol, scope=Scope.APP)
```

**After (3.0):**
```python
from modern_di import providers

alias = providers.Alias(DatabaseProtocol)
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
    create_resource,
    scope=Scope.REQUEST,
    cache_settings=providers.CacheSettings(finalizer=lambda resource: resource.close()),
)
```

**After (3.0):**
```python
factory = providers.Factory(
    create_resource,
    scope=Scope.REQUEST,
    cache=providers.CacheSettings(finalizer=lambda resource: resource.close()),
)
```

### 4. `validate` runs at container entry, on by default

The final 3.0 form differs from what 2.x signals in two ways, so read this one carefully.

**The signature.** In 2.x, `Container`'s `validate` argument is `bool | None = None`: unset (`None`)
skips validation but emits `UnvalidatedContainerWarning`; `False` skips it silently; `True` enables
it. In 3.0, the parameter is a plain `validate: bool = True` — the `None` sentinel is gone.
Passing `validate=False` still means "off"; there is no other spelling to adopt for the unset case,
because unset now *is* the default-on case.

**The timing.** In 2.x, `validate=True` validates **eagerly at construction** — `Container(...)`
itself raises `ValidationFailedError` if the graph is broken. In 3.0, validation never runs in
`__init__`. It runs once, at container **entry** — `open()`, or `with`/`async with` (which call
`open()`) — so an invalid graph raises there instead. This lets a framework integration register
its own providers (e.g. via `add_providers`) after construction and still have the complete graph
validated before first use. `validate=True` is **not eager**: if you need a construction-time
check, call `container.validate()` explicitly right after building it.

This timing change has no 2.x warning: an explicit `validate=True` caller in 2.x sees no
deprecation notice, because from 2.x's perspective that call already validates and already
succeeds — 2.x has nothing to warn about a timing it doesn't yet have. `UnvalidatedContainerWarning`
only ever covered the *unset* case (2.x's "no explicit `validate=` argument" state); it says nothing
about when validation happens once enabled. Escalating it to an error still gets you a 2.x-clean
signal for switching the *default* to on — it does not, and cannot, warn you about the *timing*
move for callers who already pass `validate=True`.

**Before (2.x):**
```python
# UnvalidatedContainerWarning: This root container was created without an
# explicit `validate` argument. modern-di 3.0 runs validate() at container
# entry by default. Pass validate=True to adopt the 3.0 behavior now, or
# validate=False to keep validation off.
container = Container(scope=Scope.APP, groups=[MyGroup])
container.resolve(MyService)

# Explicit opt-in — validates immediately, no warning, at construction:
container = Container(scope=Scope.APP, groups=[MyGroup], validate=True)  # raises here if broken
```

**After (3.0):**
```python
# validate is on by default; it runs once at open(), not at construction.
with Container(scope=Scope.APP, groups=[MyGroup]) as container:
    # validate() already ran here — raises ValidationFailedError before this
    # block is entered if the graph has cycles or scope-ordering problems.
    service = container.resolve(MyService)

# Opt out entirely — this spelling works identically before and after 3.0.
container = Container(scope=Scope.APP, groups=[MyGroup], validate=False)

# Want the check at construction time instead of at open()? Call it yourself.
container = Container(scope=Scope.APP, groups=[MyGroup])
container.validate()  # raises ValidationFailedError here if the graph is broken
```

Child containers (built via `build_child_container`) never validate, in either version — this
switch only affects root containers.

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

### 6. A container must be opened before use

New in 3.0, added mid-development, with **no 2.x deprecation signal at all** — 2.x has no
"unopened" state, so there was never anything for it to warn about. A freshly constructed
container now starts unopened; using it before entering it — `resolve`, `resolve_provider`,
`build_child_container` — raises `ContainerClosedError`. Enter it with `with`/`async with`, or call
`open()` directly (for a callback-style lifecycle that cannot use a `with` block), before the first
use. Child containers (from `build_child_container`) also start unopened and must be entered
themselves before they can be used.

This is the *never-opened* half of the same rule as [switch 1](#1-closed-containers-raise-instead-of-self-healing)
above (the *closed-after-use* half): **a container must be open to be used**, whether it was never
opened or was opened and then closed. Both cases raise the identical `ContainerClosedError`, with a
message that names which state applies, and both are fixed the same way.

**Before (2.x):**
```python
container = Container(scope=Scope.APP, groups=[MyGroup])
service = container.resolve(MyService)  # works — no open() call needed

child = container.build_child_container(scope=Scope.REQUEST)
value = child.resolve(SomeContextType)  # works — no open() call needed either
```

**After (3.0):**
```python
container = Container(scope=Scope.APP, groups=[MyGroup])
service = container.resolve(MyService)  # raises ContainerClosedError: not open

# Fix: enter the container first.
with Container(scope=Scope.APP, groups=[MyGroup]) as container:
    service = container.resolve(MyService)  # works

    # A child also starts unopened and must be entered before use.
    with container.build_child_container(scope=Scope.REQUEST) as child:
        value = child.resolve(SomeContextType)  # works

# Or, without a `with` block:
container = Container(scope=Scope.APP, groups=[MyGroup])
container.open()
service = container.resolve(MyService)  # works
```

Because there is no 2.x signal for this one, the [readiness recipe](#readiness-recipe-escalating-warnings-to-errors-with-filterwarnings)
below cannot surface it in advance — a green 2.x suite under that recipe still needs every
construct-then-use call site audited for a matching `with`/`open()` before it can run against 3.0.

## Readiness recipe: escalating warnings to errors with `filterwarnings`

This is the one place in the docs that lists the full `filterwarnings` escalation recipe; every
other page that mentions escalating a specific warning links back here.

This recipe covers switches 1, 2, 3, and 5 fully, and switch 4 only for the *unset-`validate`*
case — the case `UnvalidatedContainerWarning` actually warns about. It has **nothing** to say about
switch 6 (mandatory-open) or about switch 4's timing move for callers who already pass
`validate=True` explicitly: both are hard breaks with no 2.x warning to escalate. A green suite
under this recipe rules out five-and-a-half of the six switches; you still need to audit
construct-then-use call sites for `with`/`open()` (switch 6) and, if you pass `validate=True`
explicitly today, re-check any code that depends on validation happening at construction rather
than at `open()` (switch 4).

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

Every breaking change that *can* be signalled in modern-di is warned for at least one minor release
cycle before it flips or is removed at the next major. If you're on a 2.x release and see none of
the five warnings above under the readiness recipe, those five switches require no code changes on
your part.

That policy has a boundary: it only covers changes 2.x has a state to warn from. Mandatory-open
(switch 6) is a new requirement with no 2.x precedent — a 2.x container has no "unopened" state, so
there was never a warning to add. Likewise, switch 4's timing move (construction to `open()`) only
affects callers who already pass `validate=True`, a code path 2.x treats as already-correct and so
never warns about. Neither omission is an oversight in this guide; there is no signal to point to.
Upgrading to 3.0 requires opening every container you construct-then-use, in addition to a clean
run under the readiness recipe above.
