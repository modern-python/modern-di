# Bug-Hunt Audit Report — 2026-06-05

**Spec:** planning/changes/2026-06-05.01-bug-hunt-audit/design.md
**Plan:** planning/changes/2026-06-05.01-bug-hunt-audit/plan.md
**Survivors:** 42 findings post-verify, 41 after dedup

## Summary

| Bucket | Count |
|---|---|
| must-fix-now | 2 |
| should-fix-soon | 3 |
| nice-to-have | 14 |
| spec-fix | 0 |
| wont-fix | 22 |

## must-fix-now

### Singleton lock is non-reentrant — nested singleton resolution deadlocks the calling thread
- Dimension(s): logic, security
- File: modern_di/container.py:39, modern_di/providers/factory.py:156-168
- Severity: high
- Verifier confirmations: 3/3 (security framing); 3/3 (logic framing)
- Merged from two source findings: "Singleton resolution deadlocks when a creator re-enters resolve_provider for another singleton" (security) and "Singleton lock is non-reentrant — singleton creators that resolve another singleton from the same container deadlock" (logic). Same root cause, same fix.

**Description.** `Container.lock` is a plain `threading.Lock` (not `RLock`). `Factory.resolve` acquires that single per-container lock around `self._creator(**resolved_kwargs)` for every cached/singleton provider. When a creator legitimately re-enters `container.resolve_provider(other_singleton)` on the same container — a pattern explicitly documented at docs/providers/container.md:14-46 via the auto-registered `container_provider` — the nested call tries to acquire the same non-reentrant lock on the same thread and deadlocks permanently. Reproducer hangs the worker thread indefinitely; verified across all three verifier lenses including direct execution and spec review. The docs (docs/dev/decisions.md, docs/providers/factories.md) advertise the lock as a thread-safety primitive without warning that the documented Container-injection pattern can re-enter and deadlock.

**Evidence.**
```python
# modern_di/container.py:39
self.lock = threading.Lock() if use_lock else None

# modern_di/providers/factory.py:156-168
if container.lock:
    container.lock.acquire()
try:
    if cache_item.cache is not types.UNSET:
        return cache_item.cache
    instance = self._creator(**resolved_kwargs)
    cache_item.cache = instance
    return instance
finally:
    if container.lock:
        container.lock.release()
```

**Reproduction.**
```python
from modern_di import Container, providers
class B: pass
class A:
    def __init__(self, container: Container):
        self.b = container.resolve(B)
gb = providers.Factory(creator=B, cache_settings=providers.CacheSettings())
ga = providers.Factory(creator=A, cache_settings=providers.CacheSettings())
c = Container()
c.providers_registry.add_providers(ga, gb)
c.resolve(A)  # hangs forever
```

**Suggested fix.** Replace `threading.Lock` with `threading.RLock` in `Container.__init__` so the same thread can re-enter the lock when a creator transitively resolves another cached provider on the same container. Optionally also consider per-CacheItem locks to remove the head-of-line blocking discussed in the wont-fix bucket, but RLock alone is sufficient to clear the deadlock.

### `validate=True` raises ScopeNotInitializedError for any provider whose scope is deeper than the root container
- Dimension(s): logic
- File: modern_di/container.py:109-133, modern_di/providers/factory.py:131-132
- Severity: high
- Verifier confirmations: 3/3

**Description.** `Container.validate` iterates every provider and calls `provider.get_dependencies(self)` where `self` is the root container. `Factory.get_dependencies` calls `container.find_container(self.scope)`, which raises `ScopeNotInitializedError` whenever the provider's scope is deeper than the container's scope. Consequently, building a root APP container with `validate=True` (or calling `validate()` at all) is impossible whenever any provider has scope `REQUEST`/`SESSION`/`ACTION`/`STEP` — i.e., almost every realistic project layout. CLAUDE.md and the public API promise validate runs "cycle detection on the provider graph at container creation time" with no scope restriction; the implementation contradicts that promise.

**Evidence.**
```python
# modern_di/container.py (validate())
for one_provider in self.providers_registry:
    _visit(one_provider)
# ...
for dep_provider in provider.get_dependencies(self).values():
    _visit(dep_provider)

# modern_di/providers/factory.py
def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
    scoped_container = container.find_container(self.scope)
```

**Reproduction.**
```python
import dataclasses
from modern_di import Container, Group, Scope, providers

@dataclasses.dataclass(kw_only=True, slots=True)
class Dep: ...
@dataclasses.dataclass(kw_only=True, slots=True)
class Svc:
    dep: Dep

class G(Group):
    dep = providers.Factory(scope=Scope.REQUEST, creator=Dep)
    svc = providers.Factory(scope=Scope.REQUEST, creator=Svc)

Container(groups=[G], validate=True)
# ScopeNotInitializedError: Provider of scope REQUEST cannot be resolved in container of scope APP.
```

**Suggested fix.** Have `validate()` (and the validation-path of `get_dependencies`) introspect the provider's parsed kwargs directly instead of routing through `find_container`. Either give `Factory` a separate `get_static_dependencies()` that walks `_parsed_kwargs` and looks up provider types in `providers_registry` without scope enforcement, or pass a `validation=True` flag down to `get_dependencies` that skips the `find_container` call.

## should-fix-soon

### Self-reference guard missing in union-type branch of `_compile_kwargs`
- Dimension(s): logic
- File: modern_di/providers/factory.py:72-84
- Severity: medium
- Verifier confirmations: 3/3

**Description.** For single-type parameters, `_compile_kwargs` guards against direct self-reference with `if provider is self: provider = None`. The else-branch that walks `v.args` for union types (e.g., `int | SelfType`) has no equivalent guard: it breaks on the first matching provider regardless of whether that provider is the same `Factory`. Resolution then stores `self` in the resolved kwargs and `Factory.resolve` recurses indefinitely on `container.resolve_provider(self)`, producing `RecursionError` rather than a `CircularDependencyError` or a graceful fall-through to the parameter's default.

**Evidence.**
```python
# modern_di/providers/factory.py:72-84
if v.arg_type:
    provider = typing.cast(... container.providers_registry.find_provider(v.arg_type))
    if provider is self:
        provider = None
else:
    for x in v.args:
        provider = typing.cast(... container.providers_registry.find_provider(x))
        if provider:
            break  # no `if provider is self: provider = None; continue`
```

**Reproduction.**
```python
from modern_di import Container, providers

class SelfRef: ...
def make(x: int | SelfRef = 1) -> SelfRef:
    return SelfRef()

f = providers.Factory(creator=make)
c = Container()
c.providers_registry.add_providers(f)
c.resolve(SelfRef)  # RecursionError
```

**Suggested fix.** Inside the union loop, treat `provider is self` the same as "not found" so the loop continues to the next union arm (or falls through to default/error handling). Concretely:

```python
for x in v.args:
    candidate = container.providers_registry.find_provider(x)
    if candidate is not None and candidate is not self:
        provider = candidate
        break
else:
    provider = None
```

### `build_child_container` treats IntEnum members with value 0 as "scope omitted"
- Dimension(s): logic
- File: modern_di/container.py:68-79
- Severity: medium (re-classed up from low because custom IntEnum scopes are explicitly supported and tested)
- Verifier confirmations: 3/3

**Description.** `build_child_container` distinguishes "scope passed" from "scope omitted" using truthiness (`if scope and scope <= self.scope` and `if not scope`). IntEnum members whose value is 0 are falsy, so passing a custom scope of value 0 silently (a) bypasses the `InvalidChildScopeError` guard and (b) triggers the auto-increment branch, returning a child whose scope is `parent.value + 1` instead of raising. This directly violates the documented scope-ordering contract that child scope must be strictly greater than the parent's.

**Evidence.**
```python
# modern_di/container.py:68-79
if scope and scope <= self.scope:
    raise exceptions.InvalidChildScopeError(...)
if not scope:
    try:
        scope = self.scope.__class__(self.scope.value + 1)
```

**Reproduction.**
```python
import enum
from modern_di import Container

class CS(enum.IntEnum):
    ZERO = 0
    ONE = 1
    TWO = 2

c = Container(scope=CS.ONE)
child = c.build_child_container(scope=CS.ZERO)
assert child.scope == CS.TWO  # silently incremented instead of raising InvalidChildScopeError
```

**Suggested fix.** Switch the sentinel checks from truthiness to explicit `is None` / `is not None`: `if scope is not None and scope <= self.scope:` and `if scope is None:`. The `scope` parameter is already typed `enum.IntEnum | None = None`, so this is a one-line tightening of the existing contract.

### Default parameter values are bypassed when a ContextProvider exists but its value is UNSET
- Dimension(s): logic
- File: modern_di/providers/factory.py:87-97
- Severity: medium
- Verifier confirmations: 3/3

**Description.** `_compile_kwargs` raises `ArgumentResolutionError` as soon as it finds a registered `ContextProvider` whose underlying value is UNSET, *without checking whether the parameter has a default*. The symmetric branch immediately below (line 99) correctly skips raising when `v.default != UNSET`. The asymmetry means: declare `ts: datetime = SOME_DEFAULT` on a creator, register a `ContextProvider(context_type=datetime)` somewhere in the group, forget to inject the context value — and the factory refuses to construct, even though Python would happily fall back to `SOME_DEFAULT`. Removing the `ContextProvider` declaration lets the default be used, which is an unprincipled distinction.

**Evidence.**
```python
# modern_di/providers/factory.py:87-97
if provider:
    result[k] = provider
    if (
        is_kwarg_not_found
        and isinstance(provider, ContextProvider)
        and provider._find_context_value(container) is types.UNSET
    ):
        raise exceptions.ArgumentResolutionError(
            arg_name=k, arg_type=v.arg_type, bound_type=self.bound_type or self._creator
        )
```

**Reproduction.**
```python
import dataclasses, datetime
from modern_di import Container, Group, Scope, providers

DEFAULT = datetime.datetime(2024, 1, 1)

@dataclasses.dataclass(kw_only=True, slots=True)
class Svc:
    ts: datetime.datetime = DEFAULT

class G(Group):
    ts = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    svc = providers.Factory(creator=Svc)

Container(groups=[G]).resolve(Svc)  # ArgumentResolutionError; DEFAULT is ignored
```

**Suggested fix.** Gate the ContextProvider-UNSET raise on `v.default is types.UNSET`, mirroring the "no provider found" branch one block below. Concretely:

```python
if (
    is_kwarg_not_found
    and isinstance(provider, ContextProvider)
    and provider._find_context_value(container) is types.UNSET
    and v.default is types.UNSET
):
    raise exceptions.ArgumentResolutionError(...)
```

## nice-to-have

### `build_child_container` drops parent's `use_lock=False`
- Dimension(s): ux
- File: modern_di/container.py:62-81
- Severity: high (but ux dimension, so does not qualify for must-fix-now)
- Verifier confirmations: 3/3

**Description.** `Container.__init__` honors `use_lock`, but `build_child_container` does not propagate it when constructing the child. A user who explicitly opts out with `Container(use_lock=False)` silently gets locking back the moment they call `build_child_container`, undoing the opt-out documented at docs/providers/factories.md:99-105. Any cached factory at REQUEST/ACTION/STEP scope then uses a real lock on the child container even though the user requested single-threaded mode at the root.

**Evidence.**
```python
return self.__class__(scope=scope, parent_container=self, context=context)
```

**Reproduction.**
```python
from modern_di import Container, Scope
root = Container(use_lock=False)
child = root.build_child_container(scope=Scope.REQUEST)
assert root.lock is None
assert child.lock is None  # fails: child.lock is a real threading.Lock
```

**Suggested fix.** Forward `use_lock` (or equivalently `self.lock is not None`) to the child constructor: `return self.__class__(scope=scope, parent_container=self, context=context, use_lock=self.lock is not None)`.

### `container_provider` registered under `type(self)` breaks `Container` subclasses
- Dimension(s): ux
- File: modern_di/container.py:53-54
- Severity: medium
- Verifier confirmations: 3/3

**Description.** The auto-registered `container_provider` is keyed by `type(self)` rather than the base `Container` class. Subclassing `Container` (e.g., `class MyContainer(Container): pass`) maps `MyContainer -> container_provider` in the registry, but the documented auto-injection pattern at docs/providers/container.md:14-27 has creators annotate parameters as the literal `Container` class, which is then unresolvable. Resolution fails with `ArgumentResolutionError` even though the docs promise it works, and the `Self` return type on `build_child_container` indicates subclassing is a supported pattern.

**Evidence.**
```python
self.providers_registry = ProvidersRegistry()
self.providers_registry.register(type(self), container_provider)
```

**Reproduction.**
```python
from modern_di import Container, Group, providers

class MyContainer(Container): ...

class S:
    def __init__(self, di_container: Container) -> None: ...

class G(Group):
    svc = providers.Factory(creator=S)

MyContainer(groups=[G]).resolve(S)
# ArgumentResolutionError: Argument di_container of type Container cannot be resolved
```

**Suggested fix.** Register under the base `Container` class (and optionally also under `type(self)`), so the documented annotation pattern resolves regardless of subclassing.

### `Container(scope=<int>)` accepts non-IntEnum and explodes later in `__repr__`
- Dimension(s): ux
- File: modern_di/container.py:30-44
- Severity: medium
- Verifier confirmations: 2/3 (reproduce + read-real-code confirmed; spec-vs-behavior left "unknown" because the contract is only typed, not asserted)

**Description.** `Container.__init__` types `scope` as `enum.IntEnum` but does not validate it. Passing a bare int succeeds at construction; the failure surfaces later from an unrelated site such as `repr(container)`, logging, or `build_child_container` error paths with a bare `AttributeError: 'int' object has no attribute 'name'`. The error gives the user no hint that the original mistake was the `scope` kwarg.

**Evidence.**
```python
self.scope = scope
self.parent_container = parent_container
self.scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
```

**Reproduction.**
```python
from modern_di import Container
c = Container(scope=99)
repr(c)  # AttributeError: 'int' object has no attribute 'name'
```

**Suggested fix.** Add `if not isinstance(scope, enum.IntEnum): raise <TypedError>(...)` in `__init__`, naming the offending value.

### `Factory` silently accepts `kwargs` keys not present in the creator signature
- Dimension(s): ux
- File: modern_di/providers/factory.py:110-112
- Severity: medium
- Verifier confirmations: 2/3 (reproduce + read-real-code confirmed; spec-vs-behavior left "unknown")

**Description.** `Factory`'s static `kwargs` dict is merged into the call unconditionally with no validation against the parsed signature. A typo (`{'connetion_string': ...}`) surfaces only at instantiation time as a raw `TypeError: got an unexpected keyword argument 'connetion_string'`, with no provider identity, no resolution-chain context, and no "did you mean" hint. The `TypeError` also escapes the `except exceptions.ResolutionError` handler in `resolve()`, so even the existing `prepend_step` context is lost.

**Evidence.**
```python
if self._kwargs:
    result.update(self._kwargs)
return result
```

**Reproduction.**
```python
from modern_di import Container, Group, providers

def f(a: int = 1) -> int:
    return a

class G(Group):
    p = providers.Factory(creator=f, kwargs={'a': 1, 'nonexistent': 'oops'})

Container(groups=[G]).resolve(int)
# TypeError: f() got an unexpected keyword argument 'nonexistent'
```

**Suggested fix.** At `Factory.__init__` (or top of `_compile_kwargs`), detect `kwargs` keys not in `self._parsed_kwargs` (after handling `VAR_KEYWORD` parameters in the creator) and raise a typed `RegistrationError` or `ArgumentResolutionError` naming the offending key and suggesting the closest match.

### Dead assertion unreachable inside `pytest.raises` block
- Dimension(s): tests
- File: tests/test_container.py:55-62
- Severity: low
- Verifier confirmations: 3/3

**Description.** The line `assert app_container.resolve(str) is None` lives inside a `with pytest.raises(ProviderNotRegisteredError)` block. `resolve(str)` raises before the `is None` comparison runs, so the assertion is dead code. A future refactor that changed `resolve` to return None instead of raising would slip through unnoticed.

**Evidence.**
```python
with pytest.raises(
        ProviderNotRegisteredError,
        match=r"Provider of type <class 'str'> is not registered in providers registry.",
    ) as exc:
        assert app_container.resolve(str) is None
    assert exc.value.provider_type is str
```

**Reproduction.** Read the test: the `assert ... is None` is unreachable because `resolve(str)` raises before the comparison.

**Suggested fix.** Drop the misleading `assert ... is None`; just call `app_container.resolve(str)` directly inside the `with` block.

### Truthiness-only assertion in `test_func_with_union_factory` hides union-resolution behavior
- Dimension(s): tests
- File: tests/providers/test_factory.py:71-74
- Severity: medium
- Verifier confirmations: 3/3

**Description.** The test resolves a factory whose creator has `dep1: SimpleCreator | int` and returns `str(dep1)`, but only asserts `assert instance1` (truthy). Any non-empty string would pass — including `'0'` (the `int(0)` arm), `'X'`, or a future regression that picked the wrong union arm. The contract being tested (union types are resolved by walking `SignatureItem.args`) is not actually verified.

**Evidence.**
```python
def test_func_with_union_factory() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.func_with_union_factory)
    assert instance1
```

**Reproduction.** Change `func_with_union` to `return 'X'`; the test still passes.

**Suggested fix.** Assert on the actual returned string, e.g., `assert instance1 == str(SimpleCreator(dep1='original'))`, so the test exercises which union arm was selected.

### Context-manager tests do not verify close side-effects
- Dimension(s): tests
- File: tests/test_container.py:65-78
- Severity: medium
- Verifier confirmations: 3/3

**Description.** Both `test_container_sync_context_manager` and `test_container_async_context_manager` only assert `container.scope == Scope.APP/REQUEST` inside the `with`/`async with` blocks. They never register a cached provider with a finalizer, install an override, or otherwise create state that `close_sync`/`close_async` is supposed to clean up. Replacing the body of `Container.__exit__` and `__aexit__` with `pass` leaves both tests passing.

**Evidence.**
```python
def test_container_sync_context_manager() -> None:
    with Container() as container:
        assert container.scope == Scope.APP

    with container.build_child_container(scope=Scope.REQUEST) as request_container:
        assert request_container.scope == Scope.REQUEST
```

**Reproduction.** Comment out the body of `Container.__exit__` and `__aexit__` — both tests still pass.

**Suggested fix.** Register a singleton with a side-effect-tracking finalizer (e.g., one that appends to a list) inside the `with` block, then after exit assert the list contains the cached value. Repeat for the async test.

### `test_app_singleton` never verifies the finalizer actually ran
- Dimension(s): tests
- File: tests/providers/test_singleton.py:42-52
- Severity: medium
- Verifier confirmations: 3/3

**Description.** The test wires `sync_finalizer` (a no-op `def sync_finalizer(_): pass`) into the cache settings with `clear_cache=False`, then calls both `close_sync()` and `close_async()` and asserts only that the cache survived (`cache_item.cache is not UNSET`). Cache survival is purely a consequence of `clear_cache=False` and tells us nothing about whether the finalizer was invoked. A regression that skipped sync finalizers when `clear_cache=False` would slip through. Sibling tests in the same file already use a `cleaned_up` list to verify finalizer invocation, establishing the convention this test violates.

**Evidence.**
```python
def sync_finalizer(_: SimpleCreator) -> None:
    pass

async def test_app_singleton() -> None:
    app_container = Container(groups=[MyGroup])
    singleton1 = app_container.resolve_provider(MyGroup.app_singleton)
    singleton2 = app_container.resolve_provider(MyGroup.app_singleton)
    assert singleton1 is singleton2
    app_container.close_sync()
    cache_item = app_container.cache_registry.fetch_cache_item(MyGroup.app_singleton)
    assert cache_item.cache is not UNSET

    app_container.resolve_provider(MyGroup.app_singleton)
    await app_container.close_async()
```

**Reproduction.** Patch `CacheItem.close_sync`/`close_async` to early-return when `self.settings and not self.settings.clear_cache`. `test_app_singleton` still passes.

**Suggested fix.** Replace `sync_finalizer` with a finalizer that appends to a list (mirroring the rest of the file), and assert the list contains the cached value after each close.

### `test_func_with_broken_annotation` does not verify the warning is emitted
- Dimension(s): tests
- File: tests/providers/test_factory.py:77-80
- Severity: low
- Verifier confirmations: 3/3

**Description.** `types_parser.parse_creator` emits a `UserWarning` when `typing.get_type_hints` raises `NameError` (unresolved forward ref). This test exercises a creator with an unresolved forward ref but only asserts the downstream `ArgumentResolutionError`; it never asserts the warning fires. Worse, the warning fires when `MyGroup` is constructed at module import time (before any test runs), so the suggested fix must also move Factory construction inside the test body.

**Evidence.**
```python
def test_func_with_broken_annotation() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(ArgumentResolutionError, match="Argument dep1 of type None cannot be resolved"):
        app_container.resolve_provider(MyGroup.func_with_broken_annotation)
```

**Reproduction.** Remove the `warnings.warn(...)` call in `parse_creator`. This test still passes.

**Suggested fix.** Construct the offending Factory inside the test body wrapped in `pytest.warns(UserWarning, match="Failed to resolve type hints")`, then resolve and assert the `ArgumentResolutionError`.

### Cycle path order test depends on registry insertion order without comment
- Dimension(s): tests
- File: tests/test_container.py:109-115
- Severity: low
- Verifier confirmations: 2/3 (reproduce + read-real-code confirmed; spec-vs-behavior left "unknown" because there is no canonical cycle-rotation contract)

**Description.** `test_validate_detects_cycle` asserts `cycle_path == ['CycleA', 'CycleB', 'CycleA']`. The order depends on `Group.__dict__` (declaration order) and `ProvidersRegistry` insertion order; swapping the declaration order of `a` and `b` in `CycleGroup` produces an equally valid `['CycleB', 'CycleA', 'CycleB']` and fails the test despite correct cycle detection.

**Evidence.**
```python
def test_validate_detects_cycle() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(
        CircularDependencyError, match="Circular dependency detected: CycleA -> CycleB -> CycleA"
    ) as exc:
        container.validate()
    assert exc.value.cycle_path == ["CycleA", "CycleB", "CycleA"]
```

**Reproduction.** Swap declaration order of `a` and `b` in `CycleGroup`; the test fails with `['CycleB', 'CycleA', 'CycleB']`.

**Suggested fix.** Either assert the path matches any rotation of the 2-cycle (e.g., `set(exc.value.cycle_path) == {'CycleA', 'CycleB'}` plus a length check), or add a comment pinning the ordering assumption explicitly.

### `test_alias_resolve_provider` does not verify the alias actually delegated
- Dimension(s): tests
- File: tests/providers/test_alias.py:34-37
- Severity: low
- Verifier confirmations: 3/3

**Description.** The test resolves an alias and only asserts `isinstance(instance, PostgresRepository)`. Since the source provider also produces a `PostgresRepository`, this assertion would pass even if `Alias.resolve` were broken to construct a fresh instance instead of delegating through the registry. The sibling test `test_alias_delegates_to_source` performs the load-bearing identity check (`concrete is abstract`) but this one does not.

**Evidence.**
```python
def test_alias_resolve_provider() -> None:
    container = Container(groups=[MyGroup])
    instance = container.resolve_provider(MyGroup.abstract_repo)
    assert isinstance(instance, PostgresRepository)
```

**Reproduction.** Replace `Alias.resolve` body with `return self._source_type()`. This test still passes (`PostgresRepository` has a default `dsn`).

**Suggested fix.** Add `assert instance is container.resolve(PostgresRepository)` to assert delegation through the singleton-shared identity.

### Group inheritance silently drops providers declared on base classes
- Dimension(s): logic
- File: modern_di/group.py:19-21
- Severity: medium
- Verifier confirmations: 2/3 (reproduce + read-real-code confirmed; spec-vs-behavior "unknown" because Group inheritance is neither documented as supported nor explicitly forbidden)

**Description.** `Group.get_providers` walks `cls.__dict__.values()`, which only contains attributes defined directly on the class — not inherited ones. A `Group` subclass that inherits from another `Group` sees only its own providers; the parent's providers are silently dropped, with no warning or error. Whether Group inheritance is meant to be supported is ambiguous, but the current behavior is a silent footgun either way.

**Evidence.**
```python
@classmethod
def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
    return [x for x in cls.__dict__.values() if isinstance(x, AbstractProvider)]
```

**Reproduction.**
```python
from modern_di import Container, Group, providers

class A: ...
class B: ...

class Base(Group):
    a = providers.Factory(creator=A)

class Child(Base):
    b = providers.Factory(creator=B)

c = Container(groups=[Child])
c.resolve(B)  # OK
c.resolve(A)  # ProviderNotRegisteredError
```

**Suggested fix.** Either (a) walk `cls.__mro__` (skipping `Group` and `object`) and collect `AbstractProvider` attributes from each, supporting Group inheritance; or (b) raise `TypeError` in `Group.__init_subclass__` when the new subclass has a `Group` ancestor other than `Group` itself, explicitly forbidding the pattern. Pick one and document it.

### `close_sync`/`close_async` with `clear_cache=False` re-runs the finalizer on every call
- Dimension(s): logic
- File: modern_di/registries/cache_registry.py:20-35
- Severity: medium
- Verifier confirmations: 2/3 (reproduce + read-real-code confirmed; spec-vs-behavior "unknown" because the contract is ambiguous)

**Description.** `CacheItem.close_sync`/`close_async` calls `self.settings.finalizer(self.cache)` whenever `cache is not UNSET`, then calls `_clear()` which only nulls the cache when `settings.clear_cache=True`. When `clear_cache=False`, repeated `close_sync` calls — or the canonical Resource-replacement pattern from docs/migration/to-2.x.md:96-107 — call the finalizer on the same cached value over and over, double-closing resources like DB connections. There is no `finalized` flag to guard against repeated invocation.

**Evidence.**
```python
def close_sync(self) -> None:
    if self.cache is not types.UNSET and self.settings and self.settings.finalizer:
        if self.settings.is_async_finalizer:
            raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
        self.settings.finalizer(self.cache)
    self._clear()

def _clear(self) -> None:
    if self.settings and self.settings.clear_cache:
        self.cache = types.UNSET
```

**Reproduction.**
```python
from modern_di import Container, Group, providers

calls = []
class G(Group):
    f = providers.Factory(
        creator=lambda: 'r',
        cache_settings=providers.CacheSettings(clear_cache=False, finalizer=calls.append),
    )

c = Container(groups=[G])
c.resolve_provider(G.f)
c.close_sync(); c.close_sync(); c.close_sync()
assert len(calls) == 3  # finalizer fired three times on the same resource
```

**Suggested fix.** Add a `finalized: bool` flag to `CacheItem`, set it after the finalizer runs, and skip the finalizer call when already finalized. Reset the flag in `_clear` when `clear_cache=True` (so a re-resolved cache can be finalized again on the next close).

### `_compile_kwargs` uses `==` against `UNSET` sentinel instead of `is`
- Dimension(s): logic
- File: modern_di/providers/factory.py:99
- Severity: low
- Verifier confirmations: 3/3

**Description.** `if v.default == types.UNSET` should use `is`. `UnsetType.__doc__` in `modern_di/types.py` explicitly prescribes `is UNSET` / `isinstance(value, UnsetType)`, and every other UNSET comparison in the codebase uses identity. A parameter with `default=unittest.mock.ANY` (whose `__eq__` returns `True` for any comparand) currently makes this branch fire spuriously, raising `ArgumentResolutionError` instead of using the default.

**Evidence.**
```python
if v.default == types.UNSET and is_kwarg_not_found:
    suggestions = (
        container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
    )
    raise exceptions.ArgumentResolutionError(
```

**Reproduction.** Define a Factory whose creator has `dep: SomeUnregisteredType = unittest.mock.ANY`. Resolving the factory raises `ArgumentResolutionError` even though `mock.ANY` is a valid default; flipping the comparison to `is` lets it through.

**Suggested fix.** Replace `v.default == types.UNSET` with `v.default is types.UNSET`, matching the rest of the codebase.

## spec-fix

(no findings)

## wont-fix

### `groups=[NonGroupClass]` surfaces as `AttributeError`
- Dimension(s): ux
- File: modern_di/container.py:56-58
- Severity: low
- Verifier confirmations: 2/3 (one verifier classified as intended-behavior)

**Description.** Passing a non-Group class to `Container(groups=[...])` fails with a bare `AttributeError: type object 'NotAGroup' has no attribute 'get_providers'` rather than a typed `RegistrationError`. The type hint already declares `list[type[Group]] | None`, so this is a contract violation by the caller.

**Evidence.**
```python
if groups:
    for one_group in groups:
        self.providers_registry.add_providers(*one_group.get_providers())
```

Rationale: "Design principle: conservative feature set" (CLAUDE.md) argues against adding runtime guards that duplicate static typing; the annotation `groups: list[type[Group]] | None = None` already documents the contract.

### `InvalidChildScopeError.allowed_scopes` only lists parent enum's values
- Dimension(s): ux
- File: modern_di/container.py:68-73
- Severity: low
- Verifier confirmations: 2/3

**Description.** When `build_child_container` rejects a scope, `allowed_scopes` is built from `type(self.scope)`, listing only the parent's enum members. Custom IntEnum scopes are supported but invisible in the error.

**Evidence.**
```python
raise exceptions.InvalidChildScopeError(
    parent_scope=self.scope,
    child_scope=scope,
    allowed_scopes=[x.name for x in type(self.scope) if x > self.scope],
)
```

Rationale: tests/test_custom_scope.py::test_invalid_child_scope_uses_parent_enum_for_allowed_list pins this behavior with the docstring "allowed_scopes must be drawn from the parent's own enum class (MyScope), not the standard Scope enum."

### `ContextProvider` silently returns None when context value is unset
- Dimension(s): ux
- File: modern_di/providers/context_provider.py:31-35
- Severity: medium
- Verifier confirmations: 2/3

**Description.** Direct `resolve_provider` of a `ContextProvider` returns None when no context value is set, while the factory-consumer path raises `ArgumentResolutionError`. Two-track behavior.

**Evidence.**
```python
def resolve(self, container: "Container") -> types.T_co | None:
    value = self._find_context_value(container)
    if value is types.UNSET:
        return None
```

Rationale: explicitly codified in tests/providers/test_context_provider.py:40-42 (`assert app_container.resolve_provider(MyGroup.context_provider) is None`) and the return type annotation `types.T_co | None`. The factory-vs-direct asymmetry is deliberate so factories can require context (raise) or accept default-None.

### `set_context` on a type with no `ContextProvider` yields a generic "not registered" error
- Dimension(s): ux
- File: modern_di/container.py:151-159
- Severity: low
- Verifier confirmations: 2/3

**Description.** `set_context` stores a context value for any type, but unless that type has a `ContextProvider` declared, `resolve(type)` fails with a generic `ProviderNotRegisteredError`. No hint about the dangling `set_context` call.

**Evidence.**
```python
def set_context(self, context_type: type[types.T], obj: types.T) -> None:
    self.context_registry.set_context(context_type, obj)
```

Rationale: CLAUDE.md explicitly separates "`ProvidersRegistry` — type → provider mapping" from "`ContextRegistry` — type → runtime context object", with `ContextProvider` as the documented bridge. The separation is an architectural choice, not a contract violation.

### `MaxScopeReachedError` advises "custom IntEnum scope"
- Dimension(s): ux
- File: modern_di/errors.py:6-9
- Severity: low
- Verifier confirmations: 2/3

**Description.** The "go deeper, build a child container with a custom IntEnum scope whose value is higher" wording is stylistically debatable but technically correct.

**Evidence.**
```python
CONTAINER_MAX_SCOPE_REACHED_ERROR = (
    "Max scope of {parent_scope} is reached. "
    "To go deeper, build a child container with a custom IntEnum scope whose value is higher."
)
```

Rationale: CLAUDE.md "Scope hierarchy" describes Scope as a fixed-five-level IntEnum and points to custom IntEnums for application-specific extension; the existing message reflects that documented model.

### `ScopeSkippedError` suggests building the missing scope "as the root"
- Dimension(s): ux
- File: modern_di/errors.py:13-17
- Severity: low
- Verifier confirmations: 2/3

**Description.** The advice is correct but does not mention `build_child_container` or the documented APP -> SESSION -> REQUEST chaining pattern.

**Evidence.**
```python
CONTAINER_SCOPE_IS_SKIPPED_ERROR = (
    "No {provider_scope}-scope container exists in this chain; "
    "this chain starts at {container_scope}. "
    "Build a {provider_scope}-scope container as the root."
)
```

Rationale: the existing message is literally correct; CLAUDE.md documents the chain pattern but does not prescribe error message wording. Stylistic preference.

### Lambda creators silently degrade to `bound_type=None` with no warning
- Dimension(s): ux
- File: modern_di/providers/factory.py:42-56
- Severity: low
- Verifier confirmations: 2/3

**Description.** Default path infers `bound_type=None` from a lambda with no return annotation silently; only the `skip_creator_parsing=True` branch warns.

Rationale: docs/providers/factories.md describes `bound_type=None` as a legitimate documented state ("Set to None to make the provider unresolvable by type"). Tests at tests/providers/test_factory.py:174 and tests/test_container.py:26 actively use `providers.Factory(creator=lambda: ...)` and resolve by provider reference, locking in the no-warning behavior.

### Alias `scope` parameter is decorative
- Dimension(s): ux
- File: modern_di/providers/alias.py:16-27
- Severity: low
- Verifier confirmations: 2/3

**Description.** `Alias.resolve` ignores its own `scope`; the source provider's scope governs everything.

Rationale: docs/providers/alias.md:17-19 explicitly states "the practical effect of `scope` on `Alias` is limited. Setting it to match the source's scope is a reasonable convention." Behavior is documented as intentional.

### `Container.reset_override()` on a child wipes the whole shared override registry
- Dimension(s): ux
- File: modern_di/container.py:148-149
- Severity: low
- Verifier confirmations: 2/3

**Description.** `reset_override()` with no argument clears the entire shared `OverridesRegistry` regardless of which container it was called on.

Rationale: docs/testing/fixtures.md:69-75 explicitly documents: "Overrides are global — `container.override()` and `container.reset_override()` operate on the shared overrides registry, which is shared across all containers in the same tree." CLAUDE.md's Registries table marks `OverridesRegistry` as "Shared across all containers".

### Override bypasses scope guards — deeper-scope provider resolvable from shallower container
- Dimension(s): security
- File: modern_di/container.py:100-107
- Severity: medium
- Verifier confirmations: 2/3

**Description.** `resolve_provider` returns the override before invoking `provider.resolve(self)`, so an override on a shallower container for a deeper-scope provider returns successfully without firing the scope guard.

Rationale: tests/providers/test_factory.py::test_factory_overridden_request_scope explicitly registers an override for a REQUEST-scoped provider on an APP container and relies on this behavior. docs/integrations/pytest.md treats the tree-shared OverridesRegistry as the documented testing ergonomic. No "scope guard on overrides" contract is documented.

### Single container lock serializes unrelated singleton creations
- Dimension(s): security
- File: modern_di/providers/factory.py:156-168
- Severity: medium
- Verifier confirmations: 2/3

**Description.** All singletons on a container share one `container.lock`. A slow creator blocks the resolution of every other singleton on the same container across every thread.

Rationale: docs/providers/factories.md:97 explicitly endorses container-level locking ("only one instance will be created" under concurrent resolution) with `use_lock=False` as the documented opt-out. Creators are application-controlled, not untrusted input, so the "hostile creator" framing does not apply.

### OverridesRegistry is shared across siblings
- Dimension(s): security
- File: modern_di/container.py:49-55
- Severity: medium
- Verifier confirmations: 2/3

**Description.** Overrides set on one child container are immediately observed by sibling children and the parent.

Rationale: CLAUDE.md's Registries table marks OverridesRegistry as "Shared across all containers" (explicitly contrasted with the per-container CacheRegistry and ContextRegistry). docs/testing/fixtures.md has an explicit admonition documenting this.

### `close_async`/`close_sync` only resets overrides on root
- Dimension(s): security
- File: modern_di/container.py:135-143
- Severity: medium
- Verifier confirmations: 2/3

**Description.** Using `with child_container:` to scope an override does not clear it on exit; only root container exit clears the shared registry.

Rationale: docs/testing/fixtures.md:69-75 explicitly tells users "Always call `reset_override()` in a `finally` block or use a fixture that guarantees cleanup." The root-only reset is the documented contract.

### Factory kwargs compilation writes to shared `CacheItem` without holding the lock
- Dimension(s): security
- File: modern_di/providers/factory.py:114-148
- Severity: low
- Verifier confirmations: 2/3

**Description.** Two threads racing on `_ensure_kwargs_cached` can both compile and write to the shared `CacheItem`.

Rationale: each thread builds its own local provider_kwargs/static_kwargs dicts and then performs atomic reference assignments under CPython's GIL; both threads compute identical results because the providers registry is shared and stable. No "half-populated state" is observable. The instance-creation contract ("only one instance will be created") is preserved by the existing double-checked lock in `Factory.resolve`.

### `Container.validate` uses unbounded Python recursion
- Dimension(s): security
- File: modern_di/container.py:109-133
- Severity: low
- Verifier confirmations: 2/3

**Description.** `validate()` recurses via the nested `_visit` closure; a deep provider chain raises `RecursionError`.

Rationale: providers come from developer-written Group subclasses (class-level attributes), so there is no untrusted-input pathway. CLAUDE.md describes the "conservative feature set" design principle; supporting arbitrary-depth provider graphs is not a documented contract. `visiting`/`visited`/`path` are local variables that are GC'd when `RecursionError` propagates and do not leak into the Container.

### Resolution path has no cycle guard outside `validate()`
- Dimension(s): security
- File: modern_di/providers/factory.py:137-154
- Severity: low
- Verifier confirmations: 2/3

**Description.** Cycle detection only runs when `validate=True` is passed; otherwise cycles surface as `RecursionError` instead of `CircularDependencyError`.

Rationale: CLAUDE.md explicitly documents cycle detection as opt-in: "Pass `validate=True` to run cycle detection on the provider graph at container creation time (**zero cost when disabled**)." The "zero cost when disabled" phrasing makes the absence of a runtime guard an intentional trade-off.

### `types_parser` warns-and-skips on `NameError`
- Dimension(s): security
- File: modern_di/types_parser.py:60-71
- Severity: low
- Verifier confirmations: 2/3

**Description.** Unresolved forward references in annotations produce a `UserWarning` plus `type_hints={}`, deferring failure to resolution time.

Rationale: explicitly tested in tests/test_types_parser.py with `class ClassWithWrongAnnotations: def __init__(self, arg1: "WrongType", arg2: "int")` asserting `parse_creator` returns `{"arg1": SignatureItem(), "arg2": SignatureItem()}` rather than raising. The warn-and-skip is a documented contract.

### No test pins root-vs-child override-reset semantics in close
- Dimension(s): tests
- File: modern_di/container.py:135-143
- Severity: medium
- Verifier confirmations: 2/3 (third verifier classed as intended-behavior because the gap is a test omission, not a code bug)

**Description.** The root-resets, child-does-not branch in `close_*` is documented but not directly asserted by tests; a regression flipping the branch (especially in `close_async`) would go uncaught.

Rationale: code behavior matches the documented contract; this is a test-coverage gap, but the missing test would only re-verify a documented invariant. Listed in wont-fix because the spec-vs-behavior verifier explicitly classed it as intended-behavior.

### `set_context` docstring promise is not tested
- Dimension(s): tests
- File: modern_di/container.py:151-159
- Severity: medium
- Verifier confirmations: 2/3

**Description.** The docstring promises "Values set here are not seen by child containers that were already built." No test exercises the case where a parent calls `set_context` after a child has been built and then the child resolves a `ContextProvider`.

Rationale: same as above — the documented contract holds in code; the spec-vs-behavior verifier classed this as intended-behavior. Test coverage gap only.

### Singleton concurrency test uses an interned empty string
- Dimension(s): tests
- File: tests/providers/test_singleton.py:233-261
- Severity: low
- Verifier confirmations: 2/3

**Description.** `test_singleton_threading_concurrency` returns `""` from the creator. CPython interns empty strings, so the value-equality assertion provides no cache-sharing signal; only `calls == 1` does real work.

Rationale: the call-counter assertion (`calls == 1`) does correctly enforce the singleton contract — the creator must be invoked exactly once across threads. The interned-string nit is test hygiene rather than a contract gap.

### `Alias` provider ignores its own declared scope
- Dimension(s): logic
- File: modern_di/providers/alias.py:38-39
- Severity: medium
- Verifier confirmations: 2/3

**Description.** `Alias.resolve` does not call `container.find_container(self.scope)`; the source provider's scope governs resolution.

Rationale: docs/providers/alias.md explicitly documents this: "The alias does not enforce its own scope-based caching — the source provider's scope governs where the actual instance lives — so the practical effect of `scope` on `Alias` is limited. Setting it to match the source's scope is a reasonable convention." Test `test_alias_respects_source_scope` (tests/providers/test_alias.py:53) further pins delegation to the source's scope.

### `container_provider` scope is APP but resolution returns the calling container
- Dimension(s): logic
- File: modern_di/providers/container_provider.py:11-18
- Severity: low
- Verifier confirmations: 2/3

**Description.** `_ContainerProvider.resolve` returns whatever container called it, regardless of its declared `scope=Scope.APP`.

Rationale: explicitly tested at tests/providers/test_container_provider.py:9 (`request_container.resolve_provider(providers.container_provider) is request_container`). The docs example at docs/providers/container.md demonstrates the calling-container behavior. The `scope=Scope.APP` is the minimum scope so the provider is resolvable from any container, not a promise about which container is returned.
