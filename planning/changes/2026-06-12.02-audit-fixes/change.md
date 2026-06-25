---
date: 2026-06-12
slug: audit-fixes
summary: First batch of code+docs audit fixes. Plan-only; spec = the audit report.
spec: ../../../audits/2026-06-12-code-docs-audit-report.md
outcome: Fixed bugs B-1..B-11/X-1, dead code Q-2..Q-4, pinning tests Q-10..Q-15, and doc drift D-3/D-6..D-14 from the 2026-06-12 code+docs audit; shipped in PR #202.
---

# Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the selected findings from `planning/audits/2026-06-12-code-docs-audit-report.md`: bugs B-1..B-11 + X-1 (with the four design rulings), dead code Q-2/Q-3/Q-4, pinning tests Q-10..Q-15, and doc drift D-3, D-6..D-14 (D-1 closes via B-7).

**Architecture:** All work happens on a feature branch. Code fixes are TDD: each task adds a failing test, implements the fix in `modern_di/`, and commits. Doc fixes re-run the page's example after editing. Design rulings already made: B-1 = declaration-time error; B-9 = fix in code; X-1 = add closed state; B-11 = small code fix; B-7 = LIFO finalization in code; D-6 = docs+docstring only (context must NOT propagate parent→child — by design).

**Tech Stack:** Python 3.10+, zero runtime deps, `just` + `uv`, pytest (`asyncio_mode=auto`), ruff `select=["ALL"]`, `ty`. Line length 120.

**Critical run-command note (X-6):** single-file pytest runs trip the repo's 100% coverage gate. For targeted runs ALWAYS add `--no-cov`:
`uv run --no-sync pytest tests/providers/test_factory.py --no-cov -q`. Full-suite verification is `just test` (must stay at 100% coverage — every new code path needs a test).

**Test-writing rule:** classes used as creators MUST be defined at module level in test files — locally-defined classes break `typing.get_type_hints` (NameError → warn-and-skip) and the test silently tests nothing.

---

### Task 0: Branch + dead-code removal (Q-2, Q-3, Q-4)

**Files:**
- Modify: `modern_di/group.py:11-12`
- Modify: `modern_di/registries/overrides_registry.py:7,9`
- Modify: `modern_di/types_parser.py:35`

- [ ] **Step 1: Create the branch**

```bash
git checkout -b audit-fixes-2026-06-12
```

- [ ] **Step 2: Remove dead code**

In `modern_di/group.py` delete lines 11-12 (`T = typing.TypeVar("T")` and `P = typing.ParamSpec("P")`) — nothing references them.

In `modern_di/registries/overrides_registry.py` delete line 7 (`T_co = typing.TypeVar(...)`) and line 9 (`_UNSET = object()`); `fetch_override` uses `types.UNSET`, not `_UNSET`.

In `modern_di/types_parser.py` delete line 35 (`args = [typing.get_origin(arg) or arg for arg in args]`) — line 30 already applied `get_origin` to every member; the second pass is a verified no-op.

- [ ] **Step 3: Verify**

Run: `just lint-ci && just test`
Expected: all green, 150 passed, 100% coverage. (If removing the TypeVars makes an import unused, ruff will flag it — delete the now-unused `typing` import too if so.)

- [ ] **Step 4: Commit**

```bash
git add modern_di/group.py modern_di/registries/overrides_registry.py modern_di/types_parser.py
git commit -m "Remove dead code: unused TypeVars, _UNSET sentinel, no-op origin pass (Q-2, Q-3, Q-4)"
```

### Task 1: B-2 — `get_type_hints` TypeError becomes warn-and-skip

**Files:**
- Modify: `modern_di/types_parser.py:65-71` (the `except NameError` block)
- Test: `tests/test_types_parser.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_types_parser.py`; module-level helper first)

```python
import functools

def _partial_target(x: int, y: int) -> int:
    return x + y


def test_partial_creator_warns_and_skips_instead_of_crashing() -> None:
    with pytest.warns(UserWarning, match="skip_creator_parsing"):
        provider = providers.Factory(
            creator=functools.partial(_partial_target, y=1),
            bound_type=int,
            skip_creator_parsing=False,
        )
    assert provider is not None
```

(Match existing imports in the file: it already imports `pytest` and `providers`; add `functools`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_types_parser.py::test_partial_creator_warns_and_skips_instead_of_crashing --no-cov -q`
Expected: FAIL with `TypeError: functools.partial(...) is not a module, class, method, or function.`

- [ ] **Step 3: Implement** — in `modern_di/types_parser.py`, change the except clause:

```python
    except (NameError, TypeError) as e:
        warnings.warn(
            f"Failed to resolve type hints for {creator}: {e}. Dependency wiring will be skipped. "
            f"Pass skip_creator_parsing=True (with an explicit bound_type) to silence this warning.",
            UserWarning,
            stacklevel=2,
        )
        type_hints = {}
```

Check the existing `test_func_with_broken_annotation` test — it pins this warning via `pytest.warns(match=...)`; if its match string no longer matches the extended message, update the match string (the message prefix is unchanged, so it likely still passes).

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add modern_di/types_parser.py tests/test_types_parser.py
git commit -m "Catch TypeError from get_type_hints; warn-and-skip with workaround hint (B-2)"
```

### Task 2: B-4 — honest message for unannotated and union params

**Files:**
- Modify: `modern_di/errors.py` (new template), `modern_di/exceptions.py:152-174` (`ArgumentResolutionError`), `modern_di/providers/factory.py` (3 raise sites)
- Test: `tests/providers/test_factory.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/providers/test_factory.py`)

```python
def _unannotated_creator(x):  # noqa: ANN001, ANN202
    return x


def test_unannotated_param_error_explains_missing_annotation() -> None:
    factory: providers.Factory[object] = providers.Factory(creator=_unannotated_creator, bound_type=object)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(object, factory)
    with pytest.raises(exceptions.ArgumentResolutionError, match="has no usable type annotation"):
        container.resolve(object)


class _UnionDep1: ...


class _UnionDep2: ...


def _union_creator(x: _UnionDep1 | _UnionDep2) -> str:
    return str(x)


def test_union_param_error_names_the_union_members() -> None:
    factory: providers.Factory[str] = providers.Factory(creator=_union_creator)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(str, factory)
    with pytest.raises(exceptions.ArgumentResolutionError, match=r"_UnionDep1 \| _UnionDep2"):
        container.resolve(str)
```

(Adapt registration style to the file's existing pattern — if the file builds Groups instead of registering directly, declare a `Group` subclass with the factory and use `Container(groups=[...])`. The assertion is what matters: the message must say "has no usable type annotation" for the unannotated case and name both union members instead of "of type None".)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/providers/test_factory.py -k "unannotated_param_error or union_param_error" --no-cov -q`
Expected: FAIL — current message is `Argument x of type None cannot be resolved.`

- [ ] **Step 3: Implement**

`modern_di/errors.py` — add after `FACTORY_ARGUMENT_RESOLUTION_ERROR`:

```python
FACTORY_ARGUMENT_UNANNOTATED_ERROR = (
    "Argument {arg_name} has no usable type annotation, so it cannot be resolved by type. "
    "Pass it via the kwargs parameter or add a type annotation. Trying to build dependency {bound_type}."
)
```

`modern_di/exceptions.py` — extend `ArgumentResolutionError.__init__` with a `member_types` kwarg and message selection:

```python
class ArgumentResolutionError(ResolutionError):
    __slots__ = ("arg_name", "arg_type", "bound_type", "suggestions")

    def __init__(
        self,
        *,
        arg_name: str,
        arg_type: typing.Any,  # noqa: ANN401
        bound_type: typing.Any,  # noqa: ANN401
        suggestions: list[str] | None = None,
        member_types: list[type] | None = None,
    ) -> None:
        self.arg_name = arg_name
        self.arg_type = arg_type
        self.bound_type = bound_type
        self.suggestions = suggestions or []
        if arg_type is not None:
            message = errors.FACTORY_ARGUMENT_RESOLUTION_ERROR.format(
                arg_name=arg_name, arg_type=arg_type, bound_type=bound_type
            )
        elif member_types:
            joined = " | ".join(getattr(t, "__name__", str(t)) for t in member_types)
            message = errors.FACTORY_ARGUMENT_RESOLUTION_ERROR.format(
                arg_name=arg_name, arg_type=joined, bound_type=bound_type
            )
        else:
            message = errors.FACTORY_ARGUMENT_UNANNOTATED_ERROR.format(arg_name=arg_name, bound_type=bound_type)
        if self.suggestions:
            message += "\n" + errors.SUGGESTION_HEADER + "\n" + "\n".join(self.suggestions)
        super().__init__(message)
```

`modern_di/providers/factory.py` — pass `member_types=v.args` at all three `ArgumentResolutionError(...)` raise sites (`_compile_kwargs` has two — the ContextProvider-unset raise and the main raise — and `iter_validation_issues` has one).

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green (the new exceptions branch is covered by the two new tests).

- [ ] **Step 5: Commit**

```bash
git add modern_di/errors.py modern_di/exceptions.py modern_di/providers/factory.py tests/providers/test_factory.py
git commit -m "Honest ArgumentResolutionError for unannotated and union params (B-4)"
```

### Task 3: B-1 + B-3 — declaration-time errors for parameterized generics and positional-only params

**Files:**
- Modify: `modern_di/errors.py` (new template), `modern_di/exceptions.py` (new exception), `modern_di/types_parser.py` (generic branch + param loop)
- Test: `tests/test_types_parser.py` (new tests; update existing generic pins)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_types_parser.py`)

```python
class _GenericDep: ...


def _generic_param_creator(x: list[_GenericDep]) -> str:
    return str(x)


def test_parameterized_generic_param_without_default_raises_at_declaration() -> None:
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match=r"list\[.*_GenericDep\]"):
        providers.Factory(creator=_generic_param_creator)


def _generic_param_with_default(x: tuple[str, ...] = ()) -> str:
    return str(x)


def test_parameterized_generic_param_with_default_is_allowed() -> None:
    provider = providers.Factory(creator=_generic_param_with_default)
    assert provider is not None


def _pos_only_creator(x: int, /, y: int) -> int:
    return x + y


def test_positional_only_param_raises_at_declaration() -> None:
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match="positional-only"):
        providers.Factory(creator=_pos_only_creator)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_types_parser.py -k "parameterized_generic or positional_only" --no-cov -q`
Expected: first and third FAIL (`AttributeError: ... has no attribute 'UnsupportedCreatorParameterError'` or no raise); second may pass already.

- [ ] **Step 3: Implement**

`modern_di/errors.py` — add:

```python
FACTORY_UNSUPPORTED_PARAMETER_ERROR = (
    "Parameter {parameter_name!r} of {creator_name} cannot be injected: {reason}. "
    "Pass the value via the kwargs parameter, give the parameter a default, "
    "or use skip_creator_parsing=True with an explicit bound_type."
)
```

`modern_di/exceptions.py` — add after `UnknownFactoryKwargError`:

```python
class UnsupportedCreatorParameterError(RegistrationError):
    __slots__ = ("creator", "parameter_name", "reason")

    def __init__(self, *, creator: typing.Any, parameter_name: str, reason: str) -> None:  # noqa: ANN401
        self.creator = creator
        self.parameter_name = parameter_name
        self.reason = reason
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(
            errors.FACTORY_UNSUPPORTED_PARAMETER_ERROR.format(
                parameter_name=parameter_name, creator_name=creator_name, reason=reason
            )
        )
```

`modern_di/types_parser.py`:

a) Add the import `from modern_di import exceptions` (no cycle: `exceptions` imports only `errors`). Note the module imports stdlib `types` — keep names distinct.

b) `SignatureItem` gains a field recording a degraded generic:

```python
@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SignatureItem:
    arg_type: type | None = None
    args: list[type] = dataclasses.field(default_factory=list)
    is_nullable: bool = False
    default: object = UNSET
    raw_annotation: object = None
```

c) The generic branch stops degrading to the origin — it records the raw annotation and resolves nothing:

```python
        # generic — parameterized generics are not resolvable by type
        elif typing.get_origin(type_) is not None:
            result["raw_annotation"] = type_
```

(Remove the old `result["arg_type"] = typing.get_origin(type_)` / `result["args"] = list(typing.get_args(type_))` lines.)

d) In `parse_creator`'s parameter loop, add the two declaration-time checks:

```python
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise exceptions.UnsupportedCreatorParameterError(
                creator=creator,
                parameter_name=param_name,
                reason="positional-only parameters cannot be passed by keyword",
            )

        default = UNSET
        if param.default is not param.empty:
            default = param.default

        if param_name in type_hints:
            item = SignatureItem.from_type(type_hints[param_name], default=default)
        else:
            item = SignatureItem(default=default)
        if item.raw_annotation is not None and item.default is UNSET:
            raise exceptions.UnsupportedCreatorParameterError(
                creator=creator,
                parameter_name=param_name,
                reason=f"parameterized generic annotation {item.raw_annotation!r} cannot be resolved by type",
            )
        param_hints[param_name] = item
```

- [ ] **Step 4: Update existing pins.** `tests/test_types_parser.py` has tests pinning the OLD generic behavior (`list[X]` parsed to `arg_type=list`); rewrite them to pin the new contract (`raw_annotation` set, `arg_type is None`, declaration raise without default). Grep for them: `rtk proxy grep -n "get_origin\|list\[" tests/test_types_parser.py`. Do not delete coverage — convert each old assertion to the new behavior.

- [ ] **Step 5: Verify**

Run: `just lint-ci && just test`
Expected: all green, 100% coverage. If the union branch of `from_type` now has uncovered lines from the removed code, the diff is wrong — re-check step 3c only touched the generic `elif`.

- [ ] **Step 6: Commit**

```bash
git add modern_di/errors.py modern_di/exceptions.py modern_di/types_parser.py tests/test_types_parser.py
git commit -m "Declaration-time errors: parameterized generic and positional-only creator params (B-1, B-3)"
```

### Task 4: B-5 — `validate()` aggregates ResolutionError from `get_dependencies`

**Files:**
- Modify: `modern_di/container.py:132` (`_visit`)
- Test: `tests/providers/test_alias.py` (update the pin at lines 99-104), `tests/test_container.py`

- [ ] **Step 1: Write the failing test** (append to `tests/providers/test_alias.py`; reuse the file's existing class definitions where sensible)

```python
class _NotRegisteredSource: ...


class _SecondBroken: ...


def _needs_missing(x: _NotRegisteredSource) -> _SecondBroken:
    return _SecondBroken()


class _DanglingAliasGroup(Group):
    dangling = providers.Alias(source_type=_NotRegisteredSource, bound_type=_SecondBroken)


def test_validate_aggregates_dangling_alias_into_validation_failed_error() -> None:
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        Container(scope=Scope.APP, groups=[_DanglingAliasGroup], validate=True)
    assert any(isinstance(e, exceptions.AliasSourceNotRegisteredError) for e in exc_info.value.errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_alias.py::test_validate_aggregates_dangling_alias_into_validation_failed_error --no-cov -q`
Expected: FAIL — raw `AliasSourceNotRegisteredError` escapes instead of `ValidationFailedError`.

- [ ] **Step 3: Implement** — in `Container.validate`'s `_visit`, guard the dependency walk:

```python
            visiting.add(pid)
            path.append(provider)
            validation_errors.extend(provider.iter_validation_issues(self))

            try:
                dependencies = provider.get_dependencies(self)
            except exceptions.ResolutionError as exc:
                validation_errors.append(exc)
                dependencies = {}
            for dep_name, dep_provider in dependencies.items():
                ...
```

- [ ] **Step 4: Update the old pin.** `tests/providers/test_alias.py:99-104` currently expects the raw `AliasSourceNotRegisteredError` from `validate=True`. Rewrite that test to expect `ValidationFailedError` wrapping it (or delete it if the new test fully supersedes it — prefer rewriting to keep its scenario).

- [ ] **Step 5: Verify**

Run: `just lint-ci && just test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add modern_di/container.py tests/providers/test_alias.py
git commit -m "validate() aggregates dangling-alias errors into ValidationFailedError (B-5)"
```

### Task 5: B-6 — `Container.__init__` enforces scope ordering for `parent_container`

**Files:**
- Modify: `modern_di/container.py:30-46`
- Test: `tests/test_container.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_container.py`)

```python
def test_constructor_rejects_parent_with_non_increasing_scope() -> None:
    app = Container(scope=Scope.APP)
    with pytest.raises(exceptions.InvalidChildScopeError):
        Container(scope=Scope.APP, parent_container=app)
    with pytest.raises(exceptions.InvalidChildScopeError):
        Container(scope=Scope.APP, parent_container=app.build_child_container(scope=Scope.REQUEST))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_container.py::test_constructor_rejects_parent_with_non_increasing_scope --no-cov -q`
Expected: FAIL — no exception raised today.

- [ ] **Step 3: Implement** — in `Container.__init__`, right after the `isinstance(scope, enum.IntEnum)` check:

```python
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(
                parent_scope=parent_container.scope,
                child_scope=scope,
                allowed_scopes=[x.name for x in type(parent_container.scope) if x > parent_container.scope],
            )
```

(`build_child_container` is unaffected: it always passes a strictly greater scope.)

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add modern_di/container.py tests/test_container.py
git commit -m "Enforce scope ordering on the public parent_container constructor path (B-6)"
```

### Task 6: B-7 — finalizers run in reverse creation order (LIFO)

**Files:**
- Modify: `modern_di/registries/cache_registry.py` (`CacheRegistry`), `modern_di/providers/factory.py:221-223` (cache write)
- Test: `tests/providers/test_singleton.py`

- [ ] **Step 1: Write the failing test** (append to `tests/providers/test_singleton.py`; module level)

```python
_lifo_events: list[str] = []


class _LifoLeaf: ...


class _LifoMid:
    def __init__(self, leaf: _LifoLeaf) -> None:
        self.leaf = leaf


class _LifoTop:
    def __init__(self, mid: _LifoMid) -> None:
        self.mid = mid


class _LifoGroup(Group):
    leaf = providers.Factory(
        scope=Scope.APP, creator=_LifoLeaf, cache_settings=providers.CacheSettings(finalizer=lambda _: _lifo_events.append("leaf"))
    )
    mid = providers.Factory(
        scope=Scope.APP, creator=_LifoMid, cache_settings=providers.CacheSettings(finalizer=lambda _: _lifo_events.append("mid"))
    )
    top = providers.Factory(
        scope=Scope.APP, creator=_LifoTop, cache_settings=providers.CacheSettings(finalizer=lambda _: _lifo_events.append("top"))
    )


def test_finalizers_run_in_reverse_creation_order_even_with_warmup() -> None:
    _lifo_events.clear()
    container = Container(scope=Scope.APP, groups=[_LifoGroup])
    container.resolve(_LifoLeaf)  # the docs-recommended warmup pattern
    container.resolve(_LifoTop)
    container.close_sync()
    assert _lifo_events == ["top", "mid", "leaf"]
```

(Match the file's existing import style for `providers`, `CacheSettings`, `Group`, `Container`, `Scope`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_singleton.py::test_finalizers_run_in_reverse_creation_order_even_with_warmup --no-cov -q`
Expected: FAIL with `['leaf', 'top', 'mid'] != ['top', 'mid', 'leaf']` (insertion order today).

- [ ] **Step 3: Implement**

`modern_di/registries/cache_registry.py` — `CacheRegistry` tracks creation completion order and closes in reverse:

```python
@dataclasses.dataclass(kw_only=True, slots=True)
class CacheRegistry:
    _items: dict[int, CacheItem] = dataclasses.field(init=False, default_factory=dict)
    _creation_order: list[CacheItem] = dataclasses.field(init=False, default_factory=list)

    def cached_count(self) -> int:
        return sum(1 for item in self._items.values() if item.cache is not types.UNSET)

    def fetch_cache_item(self, provider: Factory[types.T_co]) -> CacheItem:
        return self._items.setdefault(provider.provider_id, CacheItem(settings=provider.cache_settings))

    def mark_created(self, cache_item: CacheItem) -> None:
        """Record creation completion; close() finalizes in reverse of this order (LIFO)."""
        self._creation_order.append(cache_item)

    async def close_async(self) -> None:
        finalizer_errors: list[BaseException] = []
        for cache_item in reversed(self._creation_order):
            try:
                await cache_item.close_async()
            except Exception as e:  # noqa: BLE001, PERF203
                finalizer_errors.append(e)
        self._creation_order.clear()
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=True)

    def close_sync(self) -> None:
        finalizer_errors: list[BaseException] = []
        for cache_item in reversed(self._creation_order):
            try:
                cache_item.close_sync()
            except Exception as e:  # noqa: BLE001, PERF203
                finalizer_errors.append(e)
        self._creation_order.clear()
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=False)
```

CAUTION on `close_sync` + async finalizer recovery: the existing contract (pinned by `test_request_singleton`) is that when `close_sync` hits an async finalizer it raises, the cache is retained, and a later `close_async` finalizes it. Clearing `_creation_order` in `close_sync` would break that recovery. Fix: only remove successfully-closed items. Replace the two methods' bodies with this pattern instead:

```python
    def close_sync(self) -> None:
        finalizer_errors: list[BaseException] = []
        remaining: list[CacheItem] = []
        for cache_item in reversed(self._creation_order):
            try:
                cache_item.close_sync()
            except exceptions.AsyncFinalizerInSyncCloseError as e:  # noqa: PERF203
                finalizer_errors.append(e)
                remaining.append(cache_item)
            except Exception as e:  # noqa: BLE001
                finalizer_errors.append(e)
        remaining.reverse()
        self._creation_order = remaining
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=False)
```

(`close_async` keeps the simple clear-all version — it can finalize everything.) `remaining.reverse()` restores creation order because the loop appended in reverse.

`modern_di/providers/factory.py` — in `resolve`'s locked creation branch, record completion:

```python
            instance = self._creator(**resolved_kwargs)
            cache_item.cache = instance
            container.cache_registry.mark_created(cache_item)
            return instance
```

- [ ] **Step 4: Verify** — run the existing finalizer tests plus the new one:

Run: `uv run --no-sync pytest tests/providers/test_singleton.py --no-cov -q`
Expected: ALL pass — including `test_request_singleton` (recovery) and the `clear_cache` dedup tests.
Then: `just lint-ci && just test`
Expected: all green, 100% coverage (the `AsyncFinalizerInSyncCloseError` branch in `close_sync` is exercised by `test_request_singleton`).

- [ ] **Step 5: Check D-1 is closed.** Read `docs/providers/lifecycle.md:60-70` and `docs/migration/from-that-depends.md:235-240` — both promise "reverse-resolve order"/"reverse order" finalization. With this fix the docs are now accurate; tweak wording only if it says literally "reverse of resolution *start* order" (the code implements reverse of creation *completion* order, which is what LIFO teardown means). If a wording tweak is needed, make it in this commit.

- [ ] **Step 6: Commit**

```bash
git add modern_di/registries/cache_registry.py modern_di/providers/factory.py tests/providers/test_singleton.py docs/providers/lifecycle.md docs/migration/from-that-depends.md
git commit -m "Finalize cached instances in reverse creation order — true LIFO teardown (B-7, closes D-1)"
```

### Task 7: B-8 — sync finalizer returning an awaitable is awaited (or rejected in sync close)

**Files:**
- Modify: `modern_di/registries/cache_registry.py` (`CacheItem.close_async`, `CacheItem.close_sync`)
- Test: `tests/providers/test_singleton.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/providers/test_singleton.py`)

```python
_awaitable_fin_events: list[str] = []


class _AwaitableFinSvc: ...


async def _real_cleanup(_: _AwaitableFinSvc) -> None:
    _awaitable_fin_events.append("cleaned")


class _AwaitableFinGroup(Group):
    svc = providers.Factory(
        scope=Scope.APP,
        creator=_AwaitableFinSvc,
        cache_settings=providers.CacheSettings(finalizer=lambda obj: _real_cleanup(obj)),
    )


async def test_sync_finalizer_returning_awaitable_is_awaited_in_async_close() -> None:
    _awaitable_fin_events.clear()
    container = Container(scope=Scope.APP, groups=[_AwaitableFinGroup])
    container.resolve(_AwaitableFinSvc)
    await container.close_async()
    assert _awaitable_fin_events == ["cleaned"]


async def test_sync_finalizer_returning_awaitable_raises_in_sync_close_then_recovers() -> None:
    _awaitable_fin_events.clear()
    container = Container(scope=Scope.APP, groups=[_AwaitableFinGroup])
    container.resolve(_AwaitableFinSvc)
    with pytest.raises(exceptions.FinalizerError):
        container.close_sync()
    assert _awaitable_fin_events == []  # nothing silently dropped
    await container.close_async()  # recovery: async close finalizes the retained cache
    assert _awaitable_fin_events == ["cleaned"]
```

(Both tests are async-friendly — `asyncio_mode=auto` runs async test functions without markers.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/providers/test_singleton.py -k "awaitable" --no-cov -q`
Expected: first FAIL (coroutine created, never awaited — `_awaitable_fin_events` stays empty, plus a RuntimeWarning); second FAIL (no raise; item incorrectly marked finalized).

- [ ] **Step 3: Implement** — in `modern_di/registries/cache_registry.py` add `import inspect` and rewrite `CacheItem.close_async`/`close_sync`:

```python
    async def close_async(self) -> None:
        if self.cache is not types.UNSET and not self.finalized and self.settings and self.settings.finalizer:
            result = self.settings.finalizer(self.cache)
            if inspect.isawaitable(result):
                await result
            self.finalized = True

        self._clear()

    def close_sync(self) -> None:
        if self.cache is not types.UNSET and not self.finalized and self.settings and self.settings.finalizer:
            if self.settings.is_async_finalizer:
                raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
            result = self.settings.finalizer(self.cache)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()  # suppress "never awaited" warning
                raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
            self.finalized = True

        self._clear()
```

Note: the raise paths intentionally skip `self.finalized = True` and never reach `_clear()`, so the cache is retained and `close_async` recovers — same contract as before. Task 6's `close_sync` loop catches `AsyncFinalizerInSyncCloseError` and keeps the item in `_creation_order`, so recovery composes.

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green. The `ty: ignore[invalid-await]` previously on the `await self.settings.finalizer(...)` line is gone — confirm `ty` passes without it.

- [ ] **Step 5: Commit**

```bash
git add modern_di/registries/cache_registry.py tests/providers/test_singleton.py
git commit -m "Await awaitables returned by sync finalizers; reject them in sync close (B-8)"
```

### Task 8: B-9 — `set_context` invalidates compiled kwargs (+ docstring per D-6 ruling)

**Files:**
- Modify: `modern_di/registries/cache_registry.py` (new method), `modern_di/container.py:169-177` (`set_context`)
- Test: `tests/providers/test_context_provider.py`

- [ ] **Step 1: Write the failing test** (append to `tests/providers/test_context_provider.py`)

```python
class _LateCtx: ...


class _NeedsLateCtx:
    def __init__(self, ctx: _LateCtx | None = None) -> None:
        self.ctx = ctx


class _LateCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_LateCtx)
    svc = providers.Factory(scope=Scope.APP, creator=_NeedsLateCtx)


def test_set_context_after_first_resolve_is_seen_by_later_resolves() -> None:
    container = Container(scope=Scope.APP, groups=[_LateCtxGroup])
    first = container.resolve(_NeedsLateCtx)
    assert first.ctx is None  # context unset, default applied
    value = _LateCtx()
    container.set_context(_LateCtx, value)
    second = container.resolve(_NeedsLateCtx)
    assert second.ctx is value
```

(Note: `svc` must NOT have `cache_settings` — a cached singleton would legitimately return the first instance. This pins the kwargs-recompilation contract for uncached factories.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_context_provider.py::test_set_context_after_first_resolve_is_seen_by_later_resolves --no-cov -q`
Expected: FAIL — `second.ctx is None` (the unset ContextProvider was baked out of the compiled kwargs forever).

- [ ] **Step 3: Implement**

`modern_di/registries/cache_registry.py` — add to `CacheRegistry`:

```python
    def invalidate_compiled_kwargs(self) -> None:
        for cache_item in self._items.values():
            cache_item.kwargs_compiled = False
            cache_item.provider_kwargs = {}
            cache_item.static_kwargs = {}
```

`modern_di/container.py` — rewrite `set_context` (the docstring rewrite implements the D-6 maintainer ruling: context does NOT propagate; a ContextProvider reads the registry of the container at its own scope):

```python
    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        """Register a runtime context value on *this* container.

        A ``ContextProvider`` reads the context registry of the container at the
        provider's own scope — context never propagates between parent and child
        containers. Set the value on the container whose scope matches the
        ``ContextProvider`` (for request-scoped context, pass ``context={...}``
        to :meth:`build_child_container` or call ``set_context`` on the request
        container). Values set after a dependent factory has already resolved
        are picked up by subsequent resolves.
        """
        self.context_registry.set_context(context_type, obj)
        self.cache_registry.invalidate_compiled_kwargs()
```

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add modern_di/registries/cache_registry.py modern_di/container.py tests/providers/test_context_provider.py
git commit -m "set_context invalidates compiled kwargs; docstring states the scope rule (B-9, D-6 ruling)"
```

### Task 9: B-10 + Q-15 — atomic group registration, no registry pollution on failure

**Files:**
- Modify: `modern_di/registries/providers_registry.py:48-53` (`add_providers`), `modern_di/container.py:58-60` (groups loop)
- Test: `tests/test_group.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_group.py`)

```python
class _DupA: ...


class _ExtraSvc: ...


class _GroupOne(Group):
    a = providers.Factory(scope=Scope.APP, creator=_DupA)


class _GroupTwo(Group):
    extra = providers.Factory(scope=Scope.APP, creator=_ExtraSvc)
    a_again = providers.Factory(scope=Scope.APP, creator=_DupA)


def test_duplicate_type_across_two_groups_raises() -> None:
    with pytest.raises(exceptions.DuplicateProviderTypeError):
        Container(scope=Scope.APP, groups=[_GroupOne, _GroupTwo])


def test_failed_group_registration_does_not_pollute_shared_registry() -> None:
    app = Container(scope=Scope.APP, groups=[_GroupOne])
    child = app.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(exceptions.DuplicateProviderTypeError):
        Container(scope=Scope.SESSION, parent_container=app, groups=[_GroupTwo])
    # the failed registration must not have leaked _ExtraSvc into the shared registry
    assert app.providers_registry.find_provider(_ExtraSvc) is None
    assert child.providers_registry.find_provider(_ExtraSvc) is None
```

(Q-15's "duplicate across two groups at Container()" pin is the first test.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_group.py -k "across_two_groups or pollute" --no-cov -q`
Expected: first PASSES already (the raise exists); second FAILS — `_ExtraSvc` leaked.

- [ ] **Step 3: Implement**

`modern_di/registries/providers_registry.py` — make `add_providers` all-or-nothing:

```python
    def add_providers(self, *args: AbstractProvider[typing.Any]) -> None:
        new_providers: dict[type, AbstractProvider[typing.Any]] = {}
        for provider in args:
            if not provider.bound_type:
                continue
            if provider.bound_type in new_providers or provider.bound_type in self._providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider.bound_type)
            new_providers[provider.bound_type] = provider

        self._providers.update(new_providers)
```

`modern_di/container.py` — register all groups in one atomic call:

```python
        if groups:
            all_providers: list[AbstractProvider[typing.Any]] = []
            for one_group in groups:
                all_providers.extend(one_group.get_providers())
            self.providers_registry.add_providers(*all_providers)
```

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add modern_di/registries/providers_registry.py modern_di/container.py tests/test_group.py
git commit -m "Atomic group registration: failed registration leaves shared registry untouched (B-10, Q-15)"
```

### Task 10: B-11 — ProvidersRegistry safe under concurrent reads during registration

**Files:**
- Modify: `modern_di/registries/providers_registry.py`
- Test: `tests/registries/test_providers_registry.py`

- [ ] **Step 1: Write the failing test** (append to `tests/registries/test_providers_registry.py`; the race is probabilistic, so pin determinism instead: snapshot iteration must tolerate concurrent mutation)

```python
import sys
import threading


class _RaceBase: ...


def test_iteration_is_safe_while_another_thread_registers() -> None:
    registry = ProvidersRegistry()
    race_types = [type(f"_Race{i}", (_RaceBase,), {}) for i in range(2000)]
    for t in race_types[:1000]:
        registry.register(t, providers.Factory(scope=Scope.APP, creator=t))

    errors_seen: list[BaseException] = []
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        def writer() -> None:
            for t in race_types[1000:]:
                registry.register(t, providers.Factory(scope=Scope.APP, creator=t))

        def reader() -> None:
            try:
                for _ in range(50):
                    list(iter(registry))
                    registry.build_suggestions(_RaceBase)
            except BaseException as e:  # noqa: BLE001
                errors_seen.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    assert errors_seen == []
```

(Adapt imports to the file's style. Dynamically-created types here are fine — they are registered with explicit `register`, not parsed.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/registries/test_providers_registry.py::test_iteration_is_safe_while_another_thread_registers --no-cov -q`
Expected: FAIL intermittently with `RuntimeError: dictionary changed size during iteration` (run it a few times if it passes once — it failed 600/600-style in the audit probe at this switch interval). If it will not fail after 5 runs, proceed anyway — the snapshot fix is still correct and the test pins the contract.

- [ ] **Step 3: Implement** — in `ProvidersRegistry`:

```python
import threading


class ProvidersRegistry:
    __slots__ = ("_lock", "_providers")

    def __init__(self) -> None:
        self._providers: dict[type, AbstractProvider[typing.Any]] = {}
        self._lock = threading.Lock()

    def __iter__(self) -> typing.Iterator[AbstractProvider[typing.Any]]:
        return iter(list(self._providers.values()))

    def register(self, provider_type: type, provider: AbstractProvider[typing.Any]) -> None:
        with self._lock:
            if provider_type in self._providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers[provider_type] = provider

    def add_providers(self, *args: AbstractProvider[typing.Any]) -> None:
        new_providers: dict[type, AbstractProvider[typing.Any]] = {}
        for provider in args:
            if not provider.bound_type:
                continue
            if provider.bound_type in new_providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider.bound_type)
            new_providers[provider.bound_type] = provider

        with self._lock:
            for provider_type in new_providers:
                if provider_type in self._providers:
                    raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers.update(new_providers)
```

And in `build_suggestions`, change the iteration line to a snapshot: `for provider in list(self._providers.values()):`. (`find_provider`/`__len__` are single dict ops — atomic under the GIL, leave them.)

Note `add_providers` must NOT call `self.register` (the lock is not reentrant). The duplicate check moves inside the lock; Task 9's atomicity is preserved.

- [ ] **Step 4: Verify**

Run: `just lint-ci && just test`
Expected: all green, 100% coverage.

- [ ] **Step 5: Commit**

```bash
git add modern_di/registries/providers_registry.py tests/registries/test_providers_registry.py
git commit -m "ProvidersRegistry: lock mutations, snapshot iteration (B-11)"
```

### Task 11: X-1 — closed containers refuse to resolve

**Files:**
- Modify: `modern_di/errors.py`, `modern_di/exceptions.py`, `modern_di/container.py`
- Test: `tests/test_container.py`; update `tests/providers/test_singleton.py` reuse-after-close pins

- [ ] **Step 1: Write the failing test** (append to `tests/test_container.py`)

```python
def test_closed_container_refuses_resolve_and_child_building() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.raises(exceptions.ContainerClosedError):
        container.resolve(Container)
    with pytest.raises(exceptions.ContainerClosedError):
        container.build_child_container(scope=Scope.REQUEST)


async def test_closed_container_async_path() -> None:
    container = Container(scope=Scope.APP)
    await container.close_async()
    with pytest.raises(exceptions.ContainerClosedError):
        container.resolve(Container)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_container.py -k "closed_container" --no-cov -q`
Expected: FAIL — resolve silently succeeds today.

- [ ] **Step 3: Implement**

`modern_di/errors.py` — add:

```python
CONTAINER_CLOSED_ERROR = (
    "Container (scope {container_scope}) is closed and can no longer resolve dependencies "
    "or build child containers. Create a new container."
)
```

`modern_di/exceptions.py` — add after `InvalidScopeTypeError`:

```python
class ContainerClosedError(ContainerError):
    __slots__ = ("container_scope",)

    def __init__(self, *, container_scope: enum.IntEnum) -> None:
        self.container_scope = container_scope
        super().__init__(errors.CONTAINER_CLOSED_ERROR.format(container_scope=container_scope.name))
```

`modern_di/container.py`:
- add `"closed"` to `__slots__`
- in `__init__`: `self.closed = False` (place with the other simple assignments)
- at the top of `resolve_provider` and `build_child_container` ONLY (`resolve` delegates to `resolve_provider`, so a check there too would leave the `resolve_provider` check uncoverable and trip the 100% gate):

```python
        if self.closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)
```

- in `close_sync` and `close_async`, mark closed even when finalizers raise:

```python
    def close_sync(self) -> None:
        if not self.parent_container:
            self.overrides_registry.reset_override()
        try:
            self.cache_registry.close_sync()
        finally:
            self.closed = True
```

(same `try/finally` shape for `close_async`). Close stays idempotent — the methods themselves never check `closed`, so the `close_sync`-fails → `close_async`-recovers contract (pinned by `test_request_singleton`) still works.

- [ ] **Step 4: Update old pins.** `tests/providers/test_singleton.py` has `test_close_re_finalizes_after_re_resolve_with_clear_cache_true` (and possibly others) that resolve after close — that behavior is now an error. Rewrite each to pin the new contract: after `close_sync()`, `resolve` raises `ContainerClosedError`. Keep the finalizer-dedup halves of those tests that operate before close. Grep for affected tests: `rtk proxy grep -n "close_sync\|close_async" tests/ -r` and review each hit that resolves afterwards.

- [ ] **Step 5: Verify**

Run: `just lint-ci && just test`
Expected: all green, 100% coverage.

- [ ] **Step 6: Commit**

```bash
git add modern_di/errors.py modern_di/exceptions.py modern_di/container.py tests/test_container.py tests/providers/test_singleton.py
git commit -m "Closed containers raise ContainerClosedError on resolve/build_child_container (X-1)"
```

### Task 12: Pinning tests Q-10..Q-14

**Files:**
- Test: `tests/providers/test_factory.py` (Q-10, Q-11), `tests/providers/test_context_provider.py` (Q-12), `tests/providers/test_alias.py` (Q-13, Q-14)

- [ ] **Step 1: Q-10 — static kwargs beat a type-matched provider** (append to `tests/providers/test_factory.py`)

```python
class _PrecedenceDep:
    def __init__(self, label: str = "from-provider") -> None:
        self.label = label


class _PrecedenceSvc:
    def __init__(self, dep: _PrecedenceDep) -> None:
        self.dep = dep


_static_dep = _PrecedenceDep(label="from-kwargs")


class _PrecedenceGroup(Group):
    dep = providers.Factory(scope=Scope.APP, creator=_PrecedenceDep)
    svc = providers.Factory(scope=Scope.APP, creator=_PrecedenceSvc, kwargs={"dep": _static_dep})


def test_static_kwargs_win_over_type_matched_provider() -> None:
    container = Container(scope=Scope.APP, groups=[_PrecedenceGroup])
    svc = container.resolve(_PrecedenceSvc)
    assert svc.dep is _static_dep
    assert svc.dep.label == "from-kwargs"
```

- [ ] **Step 2: Q-11 — creator raising mid-creation: nothing cached, retry succeeds, deps finalized** (append to `tests/providers/test_factory.py`)

```python
_flaky_state = {"raised": False}
_flaky_events: list[str] = []


class _FlakyDep: ...


class _FlakySvc:
    def __init__(self, dep: _FlakyDep) -> None:
        if not _flaky_state["raised"]:
            _flaky_state["raised"] = True
            msg = "boom"
            raise RuntimeError(msg)
        self.dep = dep


class _FlakyGroup(Group):
    dep = providers.Factory(
        scope=Scope.APP, creator=_FlakyDep, cache_settings=providers.CacheSettings(finalizer=lambda _: _flaky_events.append("dep"))
    )
    svc = providers.Factory(
        scope=Scope.APP, creator=_FlakySvc, cache_settings=providers.CacheSettings(finalizer=lambda _: _flaky_events.append("svc"))
    )


def test_creator_raising_mid_creation_caches_nothing_and_retry_succeeds() -> None:
    _flaky_state["raised"] = False
    _flaky_events.clear()
    container = Container(scope=Scope.APP, groups=[_FlakyGroup])
    with pytest.raises(RuntimeError, match="boom"):
        container.resolve(_FlakySvc)
    assert container.cache_registry.cached_count() == 1  # only the dep; the failed svc is NOT cached
    retried = container.resolve(_FlakySvc)
    assert isinstance(retried, _FlakySvc)
    container.close_sync()
    assert _flaky_events == ["svc", "dep"]  # LIFO from Task 6
```

- [ ] **Step 3: Q-12 — the provider's scope selects the context registry** (append to `tests/providers/test_context_provider.py`)

```python
class _ScopedCtx: ...


class _ScopedCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_ScopedCtx)


def test_context_provider_reads_registry_at_its_own_scope_not_resolving_container() -> None:
    value = _ScopedCtx()
    app = Container(scope=Scope.APP, groups=[_ScopedCtxGroup])
    request = app.build_child_container(scope=Scope.REQUEST, context={_ScopedCtx: _ScopedCtx()})
    # context set on the CHILD must be invisible to an APP-scoped provider
    assert request.resolve(_ScopedCtx) is None
    # context set on the container at the provider's scope is what counts
    app.set_context(_ScopedCtx, value)
    assert request.resolve(_ScopedCtx) is value
```

- [ ] **Step 4: Q-13 + Q-14 — alias chains and child→APP-cache identity** (append to `tests/providers/test_alias.py`)

```python
class _ChainImpl: ...


class _ChainIfA: ...


class _ChainIfB: ...


class _ChainGroup(Group):
    impl = providers.Factory(scope=Scope.APP, creator=_ChainImpl, cache_settings=providers.CacheSettings())
    if_a = providers.Alias(source_type=_ChainImpl, bound_type=_ChainIfA)
    if_b = providers.Alias(source_type=_ChainIfA, bound_type=_ChainIfB)


def test_alias_of_alias_resolves_to_source_and_validates() -> None:
    # all alias sources are registered, so validate() aggregation (B-5) is not in play
    container = Container(scope=Scope.APP, groups=[_ChainGroup], validate=True)
    impl = container.resolve(_ChainImpl)
    assert container.resolve(_ChainIfB) is impl
    assert container.resolve(_ChainIfA) is impl


def test_alias_resolved_from_child_returns_app_cached_singleton() -> None:
    container = Container(scope=Scope.APP, groups=[_ChainGroup])
    app_instance = container.resolve(_ChainImpl)
    request = container.build_child_container(scope=Scope.REQUEST)
    assert request.resolve(_ChainIfA) is app_instance
```

- [ ] **Step 5: Run all new tests, then full suite**

Run: `uv run --no-sync pytest tests/providers/ tests/test_group.py --no-cov -q`
Expected: all pass (these pin behavior that already exists or was fixed in Tasks 6/8/9).
Then: `just lint-ci && just test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add tests/providers/test_factory.py tests/providers/test_context_provider.py tests/providers/test_alias.py
git commit -m "Pin untested contracts: kwargs precedence, creator-failure, context scope-selection, alias chains (Q-10..Q-14)"
```

### Task 13: Doc fixes — D-3 (about-di.md crash) and D-8 (container.md output)

**Files:**
- Modify: `docs/introduction/about-di.md` ("Using modern-di" example), `docs/providers/container.md:18-26`

- [ ] **Step 1: Fix D-3.** Read the "Using modern-di" example in `docs/introduction/about-di.md`. It declares a REQUEST-scoped provider and resolves it from an APP container → `ScopeNotInitializedError`. Fix by building the request child (preferred — it teaches scopes):

```python
app_container = Container(scope=Scope.APP, groups=[Dependencies])
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    service = request_container.resolve(UserService)
```

Adapt names to what the page actually uses; keep the page's surrounding prose consistent with the change.

- [ ] **Step 2: Verify D-3 fix runs.** Copy the corrected example to `/tmp/fix_d3.py` with its imports and run `uv run --no-sync python /tmp/fix_d3.py`. Expected: exit 0.

- [ ] **Step 3: Fix D-8.** In `docs/providers/container.md:18-26`, the creator interpolates `di_container.scope` and the comment claims `"Container scope: Scope.APP"`; actual output is `"Container scope: 1"` (IntEnum `__format__`). Change the creator to use `.name` and fix the comment:

```python
        return f"Container scope: {di_container.scope.name}"
# ...
# result: "Container scope: APP"
```

- [ ] **Step 4: Verify D-8 fix runs** the same way (`/tmp/fix_d8.py`, assert the string).

- [ ] **Step 5: Commit**

```bash
git add docs/introduction/about-di.md docs/providers/container.md
git commit -m "Docs: fix crashing intro example and wrong scope rendering (D-3, D-8)"
```

### Task 14: Doc fixes — D-6 (context scope rule on three pages)

**Files:**
- Modify: `docs/providers/container.md:61-67`, `docs/troubleshooting/context-not-set.md:27-32`, `docs/migration/from-that-depends.md:276`

**Maintainer ruling:** context must NOT propagate parent→child; a `ContextProvider` reads only the context registry of the container at its own scope. Docs-only fix (the `set_context` docstring was already fixed in Task 8).

- [ ] **Step 1: Rewrite the advice on all three pages.** Read each cited section. Replace the "set context on the parent *before* building the child" framing ("Option A" on the first two pages) with the scope rule. Model text (adapt to each page's voice and example names):

> Context never propagates between containers. A `ContextProvider` reads the context registry of the container **at the provider's own scope**. For a REQUEST-scoped `ContextProvider`, set the value on the request container — either `build_child_container(scope=Scope.REQUEST, context={TenantId: tenant})` or `request_container.set_context(TenantId, tenant)`. Setting it on the parent works only when the provider's scope is the parent's scope, and build order is irrelevant either way.

On `context-not-set.md`, this replaces cause/fix #1; make sure the rewritten cause no longer contradicts the scope-selects-registry explanation already at lines 43-45 (that part is correct — align with it).

- [ ] **Step 2: Verify with a probe.** Write `/tmp/fix_d6.py` implementing the page's corrected example (REQUEST-scoped ContextProvider + `build_child_container(context={...})`) and run it. Expected: resolves the context value, exit 0.

- [ ] **Step 3: Commit**

```bash
git add docs/providers/container.md docs/troubleshooting/context-not-set.md docs/migration/from-that-depends.md
git commit -m "Docs: replace before/after-build context advice with the scope rule (D-6)"
```

### Task 15: Doc fixes — D-7 (alias.md walkthrough)

**Files:**
- Modify: `docs/providers/alias.md:69-90`

- [ ] **Step 1: Fix the walkthrough.** Between the first block (overrides `Dependencies.abstract_repo`, the alias) and the second block (overrides the source and asserts `container.resolve(Repository) is mock_for_source`), insert:

```python
container.reset_override(Dependencies.abstract_repo)
```

And add one sentence of prose before the second block:

> Note: an active override on the alias takes precedence over an override on its source for the aliased type — reset the alias override first if you want the source override to win.

- [ ] **Step 2: Verify by executing the page's blocks in order** (`/tmp/fix_d7.py`, stitched faithfully top-to-bottom). Expected: all asserts pass, exit 0.

- [ ] **Step 3: Commit**

```bash
git add docs/providers/alias.md
git commit -m "Docs: alias override walkthrough runs in page order; note precedence rule (D-7)"
```

### Task 16: Doc fixes — D-9, D-10, D-11 (troubleshooting pages quote real errors)

**Files:**
- Modify: `docs/troubleshooting/missing-provider.md`, `docs/troubleshooting/scope-chain.md`, `docs/troubleshooting/circular-dependency.md`

- [ ] **Step 1: Capture the real error texts.** Write `/tmp/fix_d9_capture.py` that triggers each error and prints it:
- missing provider: `Container(scope=Scope.APP).resolve(SomeUnregistered)` → `ProviderNotRegisteredError` (`Provider of type <class '...'> is not registered in providers registry.`) and the chain-rendered `ArgumentResolutionError` for the nested case
- scope chain: an APP-scoped provider depending on a REQUEST-scoped one, then `validate()` → `ValidationFailedError` containing `InvalidScopeDependencyError` (`Provider X (scope APP) declares parameter 'y' typed as a provider of Y at deeper scope REQUEST...`)
- circular dependency: two factories depending on each other, `Container(..., validate=True)` → `ValidationFailedError` containing `CircularDependencyError`
Run it and copy the exact output.

- [ ] **Step 2: Replace the quoted error blocks** on each page with the captured real text. For `circular-dependency.md` (D-11): the message body is right but only ever appears wrapped — show the `ValidationFailedError: Container.validate() found 1 issue(s): CircularDependencyError` wrapper line above the rendered cycle line, and state that without `validate=True` the failure surfaces as `RecursionError` (the page reportedly already says this — keep that part).

- [ ] **Step 3: Commit**

```bash
git add docs/troubleshooting/missing-provider.md docs/troubleshooting/scope-chain.md docs/troubleshooting/circular-dependency.md
git commit -m "Docs: troubleshooting pages quote the errors the library actually raises (D-9, D-10, D-11)"
```

### Task 17: Doc fixes — D-12, D-13, D-14

**Files:**
- Modify: `docs/introduction/design-decisions.md`, `docs/migration/to-2.x.md`, `docs/integrations/litestar.md:120-129`

- [ ] **Step 1: D-12.** `design-decisions.md` claims "mypy --strict" and "no `typing.cast` / `type: ignore`" — all false (the project uses `ty`, has 3 casts and 2 `ty: ignore`s). Rewrite the claim truthfully, e.g.:

> The codebase is checked with `ty` in strict configuration and ruff's full rule set; escape hatches (`typing.cast`, `ty: ignore`) are rare and localized.

- [ ] **Step 2: D-13.** `to-2.x.md` recommends `clear_cache=False` in a snippet that appears twice — but that hands out already-finalized resources after close (and with X-1 now in place, resolve-after-close raises). Update both snippets and surrounding prose to drop the `clear_cache=False` recommendation; state the default (`clear_cache=True`) is correct for the migration scenario and that `clear_cache=False` is only for caches that must survive a close *without* their finalizer leaving them unusable. Align with `factories.md:145-147` (which already says the right thing).

- [ ] **Step 3: D-14.** `litestar.md:120-129` websocket example: give the `async with` block a real statement mirroring the FastAPI page:

```python
    async with di_container.build_child_container(scope=Scope.REQUEST) as request_container:
        service = request_container.resolve(SomeService)
        await socket.send_text(service.greet())
```

(Adapt to the page's actual names; `ALL_GROUPS` is defined earlier on the page — reference it consistently.) Verify the snippet at least parses: `uv run --no-sync python -c "import ast; ast.parse(open('/tmp/fix_d14.py').read())"` with the stitched snippet.

- [ ] **Step 4: Commit**

```bash
git add docs/introduction/design-decisions.md docs/migration/to-2.x.md docs/integrations/litestar.md
git commit -m "Docs: truthful typing claims, drop clear_cache=False advice, fix websocket example (D-12, D-13, D-14)"
```

### Task 18: Final verification

- [ ] **Step 1: Full gate**

Run: `just lint-ci && just test`
Expected: all green, 100% coverage, ~165+ tests.

- [ ] **Step 2: Benchmarks still import** (they touch registry internals changed by Tasks 9/10)

Run: `uv run --no-sync pytest benchmarks/bench_kwargs_split.py benchmarks/bench_override_fastpath.py benchmarks/bench_scope_map.py --benchmark-disable --no-cov -q`
Expected: 22 passed. If `bench_kwargs_split.py` or `bench_scope_map.py` broke on registry/internal changes, fix the benchmark file (not the library).

- [ ] **Step 3: Doc examples still run.** Re-run the executable doc probes: `/tmp/fix_d3.py`, `/tmp/fix_d6.py`, `/tmp/fix_d7.py`, `/tmp/fix_d8.py`. Expected: all exit 0.

- [ ] **Step 4: Mark fixed findings.** In `planning/audits/2026-06-12-code-docs-audit-report.md`, add a line at the top of the Summary: `**Status (2026-06-12):** B-1..B-11, X-1, Q-2..Q-4, Q-10..Q-15, D-1, D-3, D-6..D-14 fixed on branch audit-fixes-2026-06-12; remaining findings (Q-1, Q-5..Q-9, X-2..X-6, G-1..G-11, D-2, D-4, D-5) deferred.`

Wait — D-2 (context-not-set.md phantom error text) overlaps Task 14/16 territory but was NOT selected. While editing `context-not-set.md` in Task 14, do not touch the lines D-2 covers unless the rewrite of cause #1 forces it; if it does, fix the quoted error text too and note D-2 as fixed in the status line. D-4/D-5 (multi-group recipe claims) stay untouched.

- [ ] **Step 5: Commit + hand off**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit report: mark fixed findings"
```

Then use superpowers:finishing-a-development-branch (merge vs PR decision belongs to the user).
