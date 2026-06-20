---
status: shipped
date: 2026-06-13
slug: audit-fixes-round2
spec: ../../../audits/2026-06-12-code-docs-audit-report.md
pr: "#203"
---

# Audit Fixes — Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 21 deferred findings from `planning/audits/2026-06-12-code-docs-audit-report.md`: code (Q-1, Q-5, Q-9, X-2, X-3, X-4, X-5), benchmarks/tooling (Q-6, Q-7, Q-8, X-6), and the documentation-gap batch (D-2, D-4, D-5, G-1…G-11).

**Architecture:** All on branch `audit-fixes-round2-2026-06-13` (already created). Code fixes are TDD. Four design decisions from the maintainer drive the work: (1) **implement None-injection** — `X | None` with no provider/default injects `None` (Q-1/G-3); (2) **X-3 keep resolving** a provider passed via `kwargs`, document it; (3) **move `--cov*` out of pyproject `addopts`** into recipes so targeted runs don't trip the gate (Q-6/X-6); (4) everything in one branch/PR.

**Tech Stack:** Python 3.10–3.14, zero runtime deps, `just` + `uv`, pytest (`asyncio_mode=auto`), ruff `select=["ALL"]`, `ty`. Line length 120.

**Run commands:** After Task 7 changes the test config, targeted runs are `uv run --no-sync pytest <path> -q` (NO `--no-cov` needed anymore — coverage leaves `addopts`). The gated full run is `just test-ci`. Until Task 7 lands, targeted runs still need `--no-cov`. Full gate this round: `just lint-ci && just test-ci`.

**Test-writing rules:** helper classes/functions used as creators MUST be module-level (locals break `typing.get_type_hints`). Exercise helper bodies via direct calls for coverage, not `# pragma: no cover` (except genuinely-unreachable defensive code, e.g. thread-race error captures — that precedent is settled).

---

### Task 1: Q-9 — `AbstractProvider.__slots__`

**Files:**
- Modify: `modern_di/providers/abstract.py`
- Modify: `modern_di/providers/factory.py` (slots line), `modern_di/providers/alias.py`, `modern_di/providers/context_provider.py`, `modern_di/providers/container_provider.py`
- Test: `tests/providers/test_factory.py`

- [ ] **Step 1: Read all five provider files** to see how each declares `__slots__` (currently `[*AbstractProvider.BASE_SLOTS, ...own...]`) and how `BASE_SLOTS` is referenced.

- [ ] **Step 2: Write the failing test** (append to `tests/providers/test_factory.py`, module level):

```python
def test_provider_instances_have_no_dict() -> None:
    factory: providers.Factory[object] = providers.Factory(creator=object, scope=Scope.APP)
    assert not hasattr(factory, "__dict__")
    with pytest.raises(AttributeError):
        factory.some_unexpected_attr = 1  # ty: ignore[unresolved-attribute]
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_factory.py::test_provider_instances_have_no_dict --no-cov -q`
Expected: FAIL — `factory.__dict__` exists today (no base `__slots__`), assignment succeeds.

- [ ] **Step 4: Implement.** In `modern_di/providers/abstract.py`, give the base real slots and remove the `BASE_SLOTS` indirection:

```python
class AbstractProvider(abc.ABC, typing.Generic[types.T_co]):
    __slots__ = ("bound_type", "provider_id", "scope")
```

(Delete the `BASE_SLOTS` ClassVar line.) Then in each subclass, declare ONLY its own slots (the base now owns scope/bound_type/provider_id — re-declaring them would raise "duplicate slot"):
- `factory.py`: `__slots__ = ("_creator", "_kwargs", "_parsed_kwargs", "cache_settings")`
- `alias.py`: `__slots__ = ("_source_type",)`
- `context_provider.py`: `__slots__ = ("_context_type",)`
- `container_provider.py`: whatever own-slots it had beyond BASE_SLOTS (read the file; if it added none, use `__slots__ = ()`).

Keep each subclass's slot tuple sorted if ruff's `RUF023` flags ordering.

- [ ] **Step 5: Run the test + full suite**

Run: `uv run --no-sync pytest tests/providers/test_factory.py::test_provider_instances_have_no_dict --no-cov -q` → PASS
Then: `just lint-ci && uv run --no-sync pytest tests/ --no-cov -q`
Expected: all green. If anything sets a non-slot attribute on a provider, it'll raise `AttributeError` — that's a real bug to surface, report it rather than reverting slots.

- [ ] **Step 6: Commit**

```bash
git add modern_di/providers/
git commit -m "AbstractProvider declares __slots__; subclasses keep only own slots (Q-9)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 2: Q-1 + G-3 — implement None-injection for `X | None`

**Files:**
- Modify: `modern_di/providers/factory.py` (`_compile_kwargs`, `iter_validation_issues`)
- Modify: `docs/providers/factories.md` (document the behavior — G-3)
- Test: `tests/providers/test_factory.py`

Context: `SignatureItem.is_nullable` (set in `types_parser.py:34` for unions containing `None`) is currently computed but never read. `Svc | None` with no registered `Svc` and no default raises `ArgumentResolutionError`. New behavior: inject `None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/providers/test_factory.py`, module level):

```python
class _OptionalDep: ...


class _NeedsOptionalSingle:
    def __init__(self, dep: _OptionalDep | None) -> None:
        self.dep = dep


class _NeedsOptionalUnion:
    def __init__(self, dep: "_OptionalDep | _OtherDep | None") -> None:
        self.dep = dep


class _OtherDep: ...


def test_optional_param_injects_none_when_no_provider() -> None:
    factory: providers.Factory[_NeedsOptionalSingle] = providers.Factory(
        creator=_NeedsOptionalSingle, scope=Scope.APP
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsOptionalSingle, factory)
    obj = container.resolve(_NeedsOptionalSingle)
    assert obj.dep is None


def test_optional_param_uses_provider_when_present() -> None:
    dep_factory: providers.Factory[_OptionalDep] = providers.Factory(creator=_OptionalDep, scope=Scope.APP)
    factory: providers.Factory[_NeedsOptionalSingle] = providers.Factory(
        creator=_NeedsOptionalSingle, scope=Scope.APP
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_OptionalDep, dep_factory)
    container.providers_registry.register(_NeedsOptionalSingle, factory)
    obj = container.resolve(_NeedsOptionalSingle)
    assert isinstance(obj.dep, _OptionalDep)


def test_optional_multi_member_union_injects_none_when_no_provider() -> None:
    factory: providers.Factory[_NeedsOptionalUnion] = providers.Factory(
        creator=_NeedsOptionalUnion, scope=Scope.APP
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsOptionalUnion, factory)
    obj = container.resolve(_NeedsOptionalUnion)
    assert obj.dep is None


def test_validate_does_not_flag_optional_param_without_provider() -> None:
    factory: providers.Factory[_NeedsOptionalSingle] = providers.Factory(
        creator=_NeedsOptionalSingle, scope=Scope.APP
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsOptionalSingle, factory)
    container.validate()  # must not raise
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --no-sync pytest tests/providers/test_factory.py -k "optional_param or optional_multi or validate_does_not_flag_optional" --no-cov -q`
Expected: the inject-None tests FAIL with `ArgumentResolutionError`; the validate test FAILS (it raises `ValidationFailedError`).

- [ ] **Step 3: Implement.** In `modern_di/providers/factory.py` `_compile_kwargs`, two edits.

(a) In the no-provider branch, inject None for nullable before raising:

```python
            if v.default is types.UNSET and is_kwarg_not_found:
                if v.is_nullable:
                    result[k] = None
                    continue
                suggestions = (
                    container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
                )
                raise exceptions.ArgumentResolutionError(
                    arg_name=k,
                    arg_type=v.arg_type,
                    bound_type=self.bound_type or self._creator,
                    suggestions=suggestions,
                    member_types=v.args,
                )
```

(b) In the ContextProvider-unset branch, also inject None for nullable before raising:

```python
                if (
                    is_kwarg_not_found
                    and isinstance(provider, ContextProvider)
                    and provider._find_context_value(container) is types.UNSET  # noqa: SLF001
                ):
                    if v.default is not types.UNSET:
                        continue
                    if v.is_nullable:
                        result[k] = None
                        continue
                    raise exceptions.ArgumentResolutionError(
                        arg_name=k,
                        arg_type=v.arg_type,
                        bound_type=self.bound_type or self._creator,
                        member_types=v.args,
                    )
```

In `iter_validation_issues`, skip nullable params (None satisfies them):

```python
            if v.default is not types.UNSET:
                continue
            if v.is_nullable:
                continue
            suggestions = ...
            yield exceptions.ArgumentResolutionError(...)
```

Note: `result[k] = None` lands in `static_kwargs` (None is not an `AbstractProvider`), so it's passed literally to the creator. No change needed in `_ensure_kwargs_cached`.

- [ ] **Step 4: Update any existing test that pinned the old "nullable raises" behavior.** Grep: `rtk proxy grep -rn "is_nullable\|union_factory\|| None" tests/`. If a test asserted `Svc | None` with no provider raises, flip it to the new inject-None contract. The `_UnionDep1 | _UnionDep2` test (no `None`, from B-4) must STILL raise — confirm it's untouched.

- [ ] **Step 5: Run the new tests + full suite**

Run: `uv run --no-sync pytest tests/ --no-cov -q` → all pass. Confirm each new branch (no-provider nullable, contextprovider-unset nullable, validate skip) is covered; if the contextprovider-unset nullable branch is uncovered, add a test with an unset `ContextProvider` typed `Svc | None`.
Then `just lint-ci`.

- [ ] **Step 6: Document (G-3).** In `docs/providers/factories.md`, in/after the section discussing parameter resolution, add a short subsection stating: a parameter annotated `X | None` (or `Optional[X]`) resolves to a registered provider for `X` if present; otherwise `None` is injected (no provider and no default required). Verify with a runnable snippet copied to `/tmp/g3.py` and executed.

- [ ] **Step 7: Commit**

```bash
git add modern_di/providers/factory.py tests/providers/test_factory.py docs/providers/factories.md
git commit -m "Inject None for X|None params with no provider; wire is_nullable; document (Q-1, G-3)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3: X-2 — `skip_creator_parsing=True` missing kwargs → DI error

**Files:**
- Modify: `modern_di/providers/factory.py` (`resolve`)
- Test: `tests/providers/test_factory.py`

Context: with `skip_creator_parsing=True` and required creator params not supplied via `kwargs`, resolution calls `self._creator(**resolved_kwargs)` and dies with a raw `TypeError` carrying no DI context.

- [ ] **Step 1: Write the failing test** (append to `tests/providers/test_factory.py`):

```python
def _needs_two_args(a: int, b: int) -> int:
    return a + b


def test_skip_creator_parsing_missing_args_raises_di_error() -> None:
    factory: providers.Factory[int] = providers.Factory(
        creator=_needs_two_args, bound_type=int, skip_creator_parsing=True, kwargs={"a": 1}
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(int, factory)
    with pytest.raises(exceptions.CreatorCallError) as exc_info:
        container.resolve(int)
    assert "_needs_two_args" in str(exc_info.value)
    assert isinstance(exc_info.value, exceptions.ResolutionError)
    assert _needs_two_args(1, 2) == 3  # exercise helper body
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_factory.py::test_skip_creator_parsing_missing_args_raises_di_error --no-cov -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'CreatorCallError'` (and currently a raw `TypeError` would escape).

- [ ] **Step 3: Implement.**

`modern_di/errors.py` — add:

```python
CREATOR_CALL_ERROR = "Failed to call creator {creator_name}: {error}. Check kwargs and skip_creator_parsing usage."
```

`modern_di/exceptions.py` — add after `ArgumentResolutionError` (it's a `ResolutionError` so it joins the dependency-chain rendering):

```python
class CreatorCallError(ResolutionError):
    __slots__ = ("creator", "original_error")

    def __init__(self, *, creator: typing.Any, original_error: Exception) -> None:  # noqa: ANN401
        self.creator = creator
        self.original_error = original_error
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(errors.CREATOR_CALL_ERROR.format(creator_name=creator_name, error=original_error))
```

`modern_di/providers/factory.py` — wrap BOTH creator-call sites in `resolve` (the non-cached `return self._creator(**resolved_kwargs)` and the cached `instance = self._creator(**resolved_kwargs)`). Add a helper and use it:

```python
    def _call_creator(self, resolved_kwargs: dict[str, typing.Any]) -> types.T_co:
        try:
            return self._creator(**resolved_kwargs)
        except TypeError as exc:
            raise exceptions.CreatorCallError(creator=self._creator, original_error=exc) from exc
```

Replace the two direct `self._creator(**resolved_kwargs)` calls with `self._call_creator(resolved_kwargs)`. The existing `except exceptions.ResolutionError` wrapper around kwargs compilation does NOT cover the creator call (it's outside that try for the non-cached path; for the cached path the creator call is inside the lock). `CreatorCallError` is a `ResolutionError`, so add `prepend_step` handling: ensure the creator-call errors also get the resolution step prepended. Simplest: in `resolve`, wrap the creator calls so a `CreatorCallError` gets `prepend_step(self._resolution_step())` like other `ResolutionError`s. Concretely, for the non-cached branch:

```python
        if not self.cache_settings:
            try:
                return self._call_creator(resolved_kwargs)
            except exceptions.ResolutionError as exc:
                exc.prepend_step(self._resolution_step())
                raise
```

and for the cached branch, wrap the `instance = self._call_creator(...)` similarly inside the lock.

CAUTION: only wrap `TypeError` from the creator call, not arbitrary exceptions — a creator that legitimately raises `ValueError`/`RuntimeError` (e.g. the Q-11 flaky-creator test) must propagate unchanged. `TypeError` specifically is the "bad call signature" signal. Verify the Q-11 test (`test_creator_raising_mid_creation...` raising `RuntimeError`) still sees its `RuntimeError`, not a wrapped error.

- [ ] **Step 4: Run the new test + full suite**

Run: `uv run --no-sync pytest tests/ --no-cov -q` → all pass (Q-11's RuntimeError test must still pass unchanged).
Then `just lint-ci`.

- [ ] **Step 5: Commit**

```bash
git add modern_di/errors.py modern_di/exceptions.py modern_di/providers/factory.py tests/providers/test_factory.py
git commit -m "Wrap creator-call TypeError in CreatorCallError with DI context (X-2)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4: X-4 — `validate()` does not enforce an Alias's decorative scope

**Files:**
- Modify: `modern_di/providers/alias.py` (override `iter_validation_issues` / signal scope-exempt) OR `modern_di/container.py` (`validate` skip alias edge)
- Test: `tests/providers/test_alias.py`

Context: `Alias.scope` is decorative (resolution never consults it — `alias.py` delegates to the source). But `Container.validate`'s `_visit` checks `dep_provider.scope > provider.scope` for ALL dependencies, so an Alias whose (default APP) scope is shallower than its source's deeper scope is flagged with `InvalidScopeDependencyError` — a false positive, since resolution works.

- [ ] **Step 1: Write the failing test** (append to `tests/providers/test_alias.py`):

```python
class _DeepImpl: ...


class _ShallowIface: ...


class _AliasScopeGroup(Group):
    impl = providers.Factory(scope=Scope.REQUEST, creator=_DeepImpl)
    iface = providers.Alias(source_type=_DeepImpl, bound_type=_ShallowIface)  # default APP scope


def test_validate_does_not_flag_alias_whose_scope_is_shallower_than_source() -> None:
    app = Container(scope=Scope.APP, groups=[_AliasScopeGroup])
    app.validate()  # must NOT raise InvalidScopeDependencyError for the alias->impl edge
    request = app.build_child_container(scope=Scope.REQUEST)
    assert isinstance(request.resolve(_ShallowIface), _DeepImpl)  # resolution works
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_alias.py::test_validate_does_not_flag_alias_whose_scope_is_shallower_than_source --no-cov -q`
Expected: FAIL — `ValidationFailedError` containing `InvalidScopeDependencyError`.

- [ ] **Step 3: Implement.** The scope check lives in `container.py` `validate._visit`. The cleanest fix is to skip the scope-ordering check for the dependency edges of providers whose scope is decorative. Give `AbstractProvider` a class attribute flag and have `Alias` set it:

`modern_di/providers/abstract.py` — add a class-level flag (after the slots line; class vars don't need a slot):

```python
    enforces_dependency_scope: typing.ClassVar[bool] = True
```

`modern_di/providers/alias.py` — in `Alias`, add:

```python
    enforces_dependency_scope = False
```

`modern_di/container.py` — in `validate._visit`, guard the scope check:

```python
            for dep_name, dep_provider in dependencies.items():
                if provider.enforces_dependency_scope and dep_provider.scope > provider.scope:
                    validation_errors.append(
                        exceptions.InvalidScopeDependencyError(...)
                    )
                _visit(dep_provider)
```

(This keeps full cycle/structure traversal; only the scope-ordering assertion is skipped for aliases. The source provider `_DeepImpl` is still visited and its own real dependencies still scope-checked.)

- [ ] **Step 4: Run + full suite.** `uv run --no-sync pytest tests/ --no-cov -q` → green. Ensure an existing test that DOES expect `InvalidScopeDependencyError` for a real Factory→deeper-Factory edge still passes (that's `enforces_dependency_scope=True`). `just lint-ci`.

- [ ] **Step 5: Commit**

```bash
git add modern_di/providers/abstract.py modern_di/providers/alias.py modern_di/container.py tests/providers/test_alias.py
git commit -m "validate() exempts Alias decorative scope from scope-order check (X-4)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 5: X-5 — Alias hops appear in the resolution-error chain

**Files:**
- Modify: `modern_di/providers/alias.py` (`resolve` wraps delegation with a resolution step)
- Test: `tests/providers/test_alias.py`

Context: a `ResolutionError` raised while resolving through an Alias does not include the alias in the rendered dependency chain (Factory edges do, via `prepend_step`). (Note: a true mutual-alias *cycle* still surfaces as `RecursionError` without `validate()` — that runtime-guard absence is a documented wont-fix; this task only adds chain context to alias hops, the new angle.)

- [ ] **Step 1: Write the failing test** (append to `tests/providers/test_alias.py`):

```python
class _MissingForAlias: ...


class _AliasTargetIface: ...


class _NeedsMissing:
    def __init__(self, x: _MissingForAlias) -> None:
        self.x = x


class _AliasChainErrGroup(Group):
    impl = providers.Factory(scope=Scope.APP, creator=_NeedsMissing)  # _MissingForAlias not registered
    iface = providers.Alias(source_type=_NeedsMissing, bound_type=_AliasTargetIface)


def test_alias_appears_in_resolution_error_chain() -> None:
    container = Container(scope=Scope.APP, groups=[_AliasChainErrGroup])
    with pytest.raises(exceptions.ArgumentResolutionError) as exc_info:
        container.resolve(_AliasTargetIface)
    rendered = str(exc_info.value)
    assert "_AliasTargetIface" in rendered  # the alias hop is shown in the chain
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/providers/test_alias.py::test_alias_appears_in_resolution_error_chain --no-cov -q`
Expected: FAIL — the rendered chain shows `_NeedsMissing` but not the `_AliasTargetIface` alias hop.

- [ ] **Step 3: Implement.** In `modern_di/providers/alias.py`, add a resolution step and wrap delegation:

```python
    def _resolution_step(self) -> "exceptions.ResolutionStep":
        name = self.bound_type.__name__ if self.bound_type else repr(self)
        return exceptions.ResolutionStep(scope=self.scope, name=name)

    def resolve(self, container: "Container") -> types.T_co:
        try:
            return container.resolve_provider(self._find_source(container))
        except exceptions.ResolutionError as exc:
            exc.prepend_step(self._resolution_step())
            raise
```

(Import note: `exceptions` is already imported in `alias.py`. `ResolutionStep` lives in `modern_di.exceptions`.) Mind that `bound_type` may be `None` (decorative alias) — the `repr(self)` fallback handles it.

- [ ] **Step 4: Run + full suite.** `uv run --no-sync pytest tests/ --no-cov -q` → green; confirm existing alias tests (chain resolve, override) still pass. `just lint-ci`.

- [ ] **Step 5: Commit**

```bash
git add modern_di/providers/alias.py tests/providers/test_alias.py
git commit -m "Alias prepends a resolution step so it appears in error chains (X-5)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 6: Q-5 — centralize the two static inline exception messages

**Files:**
- Modify: `modern_di/errors.py`, `modern_di/exceptions.py`
- Test: existing tests cover these exceptions; add an assertion only if coverage requires.

Context: five exception classes build messages inline. Three are inherently dynamic (`UnknownFactoryKwargError` loops keys; `ValidationFailedError` counts/renders; `FinalizerError` lists errors) — leave those with a brief `# message is dynamic` comment. Two are static and should use `errors.py` templates for consistency: `AsyncFinalizerInSyncCloseError` and `GroupInstantiationError`.

- [ ] **Step 1: Implement.** `modern_di/errors.py` — add:

```python
ASYNC_FINALIZER_IN_SYNC_CLOSE_ERROR = (
    "Cannot run async finalizer for {finalizer_type} during sync close. "
    "Use `await container.close_async()` (or `async with container:`) instead."
)
GROUP_INSTANTIATION_ERROR = "{group_name} cannot be instantiated"
```

`modern_di/exceptions.py` — `AsyncFinalizerInSyncCloseError.__init__`:

```python
        super().__init__(
            errors.ASYNC_FINALIZER_IN_SYNC_CLOSE_ERROR.format(finalizer_type=finalizer_type.__name__)
        )
```

`GroupInstantiationError.__init__`:

```python
        super().__init__(errors.GROUP_INSTANTIATION_ERROR.format(group_name=group_name))
```

For the three dynamic ones, add a one-line comment `# message built dynamically; not templated` above each inline `super().__init__(...)`.

- [ ] **Step 2: Run + full suite.** `uv run --no-sync pytest tests/ --no-cov -q` → green (message text unchanged, existing tests that match on these strings still pass; verify `AsyncFinalizerInSyncCloseError` text byte-for-byte matches the old message). `just lint-ci`.

- [ ] **Step 3: Commit**

```bash
git add modern_di/errors.py modern_di/exceptions.py
git commit -m "Centralize the two static exception messages into errors.py templates (Q-5)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 7: Q-6 + X-6 + Q-7 + Q-8 — coverage config out of addopts; benchmarks collectible and correct

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`)
- Modify: `Justfile` (recipes)
- Modify: `.github/workflows/_checks.yml` (pytest invocation)
- Rename: `benchmarks/bench_*.py` → `benchmarks/test_bench_*.py`
- Modify: `benchmarks/test_bench_scope_map.py` (Q-7), `benchmarks/test_bench_kwargs_split.py` (Q-8)

- [ ] **Step 1: Move coverage out of `addopts` and pin testpaths.** In `pyproject.toml` `[tool.pytest.ini_options]`, change:

```toml
[tool.pytest.ini_options]
addopts = ""
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["."]
asyncio_default_fixture_loop_scope = "function"
```

(Drop the `--cov*` flags; `testpaths = ["tests"]` keeps the default run scoped to tests/ so renamed benchmarks aren't collected by a bare `pytest`.)

- [ ] **Step 2: Add recipes.** In `Justfile`, replace the `test`/`test-branch` block with:

```
test *args:
    uv run --no-sync pytest {{ args }}

test-ci:
    uv run --no-sync pytest --cov=. --cov-report term-missing --cov-report xml --cov-fail-under=100

test-branch:
    uv run --no-sync pytest --cov=. --cov-branch --cov-fail-under=100

bench:
    uv run --no-sync pytest benchmarks/ --benchmark-only
```

(`just test tests/foo.py` now runs clean with no coverage gate; `just test-ci` is the gated full run; `just bench` runs benchmarks by explicit path, overriding testpaths.)

- [ ] **Step 3: Point CI at the gated recipe.** In `.github/workflows/_checks.yml`, change the pytest step `- run: just test . --cov=. --cov-report xml` to:

```yaml
      - run: just test-ci
```

(The `--cov-report xml` is now inside `test-ci`. Read the file first to keep surrounding YAML/codecov-upload steps intact.)

- [ ] **Step 4: Rename benchmark files** so they're collectible (their functions are already `test_*`):

```bash
git mv benchmarks/bench_kwargs_split.py benchmarks/test_bench_kwargs_split.py
git mv benchmarks/bench_override_fastpath.py benchmarks/test_bench_override_fastpath.py
git mv benchmarks/bench_scope_map.py benchmarks/test_bench_scope_map.py
```

Update the in-file documented run command (in `test_bench_override_fastpath.py`, the comment showing `uv run pytest benchmarks/ --benchmark-only ...`) to the working form `just bench` (or `uv run --no-sync pytest benchmarks/ --benchmark-only`). Update `benchmarks/__init__.py` or any imports if they referenced the old module names (grep: `rtk proxy grep -rn "bench_kwargs_split\|bench_override_fastpath\|bench_scope_map" .`).

- [ ] **Step 5: Q-7 fix** in `benchmarks/test_bench_scope_map.py` (~line 34): the `errors.CONTAINER_SCOPE_IS_SKIPPED_ERROR.format(provider_scope=...)` call is missing the now-required `{container_scope}` field → latent `KeyError`. Replace that simulated raise with a plain `RuntimeError("skipped scope")` (the message text is irrelevant to the benchmark measurement), OR supply both fields. Read the surrounding code and pick the form that keeps the baseline meaningful.

- [ ] **Step 6: Q-8 fix** in `benchmarks/test_bench_kwargs_split.py`: (a) remove the dead container setup (~lines 98–116) that is discarded by a later rebinding (~line 125) — read the file and excise only the genuinely-unused block; (b) fix the wrong-variable check (~line 183) `isinstance(k, AbstractProvider)` → `isinstance(v, AbstractProvider)` to match the real classification (the value, not the key).

- [ ] **Step 7: Verify.**

Run: `uv run --no-sync pytest -q` (bare — should collect ONLY tests/, run clean, no coverage gate noise).
Run: `just test-ci 2>&1 | tail -3` → 100% coverage gate passes on tests/.
Run: `just bench 2>&1 | tail -3` → benchmarks collect and run (the 22 benchmark tests).
Run: `just lint-ci` → clean.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml Justfile .github/workflows/_checks.yml benchmarks/
git commit -m "Coverage flags out of addopts into recipes; benchmarks collectible; fix bench KeyError and wrong-var isinstance (Q-6, X-6, Q-7, Q-8)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 8: Docs — D-2, D-4, D-5 (false claims / phantom errors)

**Files:**
- Modify: `docs/troubleshooting/context-not-set.md` (D-2)
- Modify: `docs/recipes/multi-group.md`, `docs/recipes/request-scoped-engine.md` (D-4)
- Modify: `docs/recipes/multi-group.md` (D-5)

- [ ] **Step 1: D-2** — the top of `docs/troubleshooting/context-not-set.md` (around lines 7–11) quotes a phantom `RuntimeError: ContextProvider for <class 'TenantId'> has no value in container...` that the library never raises. Capture the REAL error: a required (non-defaulted) context-typed param with unset context resolves to a chain-rendered `ArgumentResolutionError` (write `/tmp/d2.py`, trigger it, copy the exact text). Replace the phantom block with the real one, keeping the surrounding (already-correct, D-6-fixed) prose intact.

- [ ] **Step 2: D-4** — in `docs/recipes/multi-group.md` (~lines 85–87: "Type collisions are silent" / "second registration wins") and `docs/recipes/request-scoped-engine.md` (~line 76: "the second one would shadow the first"), the claim is false: registering two providers for the same `bound_type` raises `DuplicateProviderTypeError` at `Container(...)` time. Rewrite both to state that duplicate types raise (link to `troubleshooting/duplicate-type-error.md`), and describe the real fix (distinct `bound_type`s or `kwargs` wiring). Verify by triggering the error in `/tmp/d4.py`.

- [ ] **Step 3: D-5** — in `docs/recipes/multi-group.md` (~line 85), the claim "if two groups define an attribute with the same name you get `ValueError`" is wrong for `Container`: it keys on `bound_type`, not attribute names. The `ValueError` belongs to `modern-di-pytest`'s `expose()` (a sibling package). Rewrite to clarify: `Container` does not check attribute names; the duplicate-name `ValueError` only occurs in `modern-di-pytest`'s `expose(*groups)`. Verify the `Container` side (same attr name, distinct types → no `ValueError`) in `/tmp/d5.py`.

- [ ] **Step 4: `just lint-ci`** (eof-fixer/ruff touch markdown) → clean.

- [ ] **Step 5: Commit**

```bash
git add docs/troubleshooting/context-not-set.md docs/recipes/multi-group.md docs/recipes/request-scoped-engine.md
git commit -m "Docs: real unset-context error, duplicate-type raises not shadows, ValueError is pytest-expose not Container (D-2, D-4, D-5)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 9: Docs — G-1, G-9, X-3 (creator-signature matrix, creator-failure, provider-as-kwarg)

**Files:**
- Modify: `docs/providers/factories.md`

- [ ] **Step 1: G-1 — creator-signature support matrix.** Add a subsection to `docs/providers/factories.md` documenting which creator parameter shapes are supported, verified against current behavior (write `/tmp/g1.py` exercising each):
  - resolvable by type: a plain class/annotated param with a registered provider;
  - `X | None` / `Optional[X]` → provider if present else `None` (cross-reference G-3 from Task 2);
  - parameterized generics (`list[Svc]`) and positional-only params → raise `UnsupportedCreatorParameterError` at declaration unless supplied via `kwargs` or given a default (the B-1/B-3 behavior);
  - unannotated params → `ArgumentResolutionError` at resolve unless supplied via `kwargs`;
  - `functools.partial` / signatures `get_type_hints` can't resolve → warn-and-skip wiring (pass `skip_creator_parsing=True` + `bound_type`);
  - `skip_creator_parsing=True` → no wiring; you must supply all args via `kwargs` (else `CreatorCallError`, Task 3).

- [ ] **Step 2: G-9 — creator-failure semantics.** Add a short note: if a creator raises during resolution, nothing is cached, already-resolved dependencies are finalized at container close, and the next resolve retries. (Pinned by `tests/providers/test_factory.py::test_creator_raising_mid_creation...`.) Verify with `/tmp/g9.py`.

- [ ] **Step 3: X-3 — provider passed via kwargs.** Add a note: passing an `AbstractProvider` instance as a `kwargs` value is treated as explicit wiring — it is resolved, and the resolved value is injected (not the provider object). Verify with `/tmp/x3.py`.

- [ ] **Step 4: `just lint-ci`** → clean. Run every `/tmp/g*.py` and `/tmp/x3.py` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add docs/providers/factories.md
git commit -m "Docs: creator-signature matrix, creator-failure semantics, provider-as-kwarg wiring (G-1, G-9, X-3)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 10: Docs — G-5, G-6, G-7, G-8 (exceptions, close-failure, container_provider, thread-safety)

**Files:**
- Create: `docs/providers/errors-and-exceptions.md` (G-5) — or extend an existing concept page; check `mkdocs.yml` nav and follow the docs structure.
- Modify: `docs/providers/lifecycle.md` (G-6), `docs/providers/container.md` (G-7), `docs/introduction/design-decisions.md` (G-8)
- Modify: `mkdocs.yml` (nav entry for the new page)

- [ ] **Step 1: G-5 — exception taxonomy.** Create `docs/providers/errors-and-exceptions.md` documenting the hierarchy from `modern_di/exceptions.py`: root `ModernDIError(RuntimeError)`; branches `ContainerError` (incl. `InvalidChildScopeError`, `MaxScopeReachedError`, `ScopeNotInitializedError`, `ScopeSkippedError`, `InvalidScopeTypeError`, `ContainerClosedError`, `ValidationFailedError`), `ResolutionError` (incl. `ProviderNotRegisteredError`, `AliasSourceNotRegisteredError`, `ArgumentResolutionError`, `CircularDependencyError`, `CreatorCallError`), `RegistrationError` (incl. `DuplicateProviderTypeError`, `UnknownFactoryKwargError`, `UnsupportedCreatorParameterError`, `InvalidScopeDependencyError`), plus `FinalizerError`, `AsyncFinalizerInSyncCloseError`, `GroupInstantiationError`. State what to catch (e.g. catch `ResolutionError` for resolution failures, `ValidationFailedError` for `validate()` results). Cross-check every name against the current `exceptions.py` (include `CreatorCallError` from Task 3). Add it to `mkdocs.yml` nav under the Providers section.

- [ ] **Step 2: G-6 — close-failure semantics.** Extend `docs/providers/lifecycle.md`'s closing section: `close_sync` on a cached resource with an async finalizer raises `AsyncFinalizerInSyncCloseError` (the cache is retained so a later `await close_async()` recovers it); finalizer errors during close are aggregated into a single `FinalizerError` and the remaining finalizers still run. Verify with `/tmp/g6.py`.

- [ ] **Step 3: G-7 — container_provider.** In `docs/providers/container.md`, state that resolving the `Container` (the auto-registered `container_provider`) returns the **calling** container — i.e. the deepest/most-specific container in the active chain (a REQUEST child resolves to itself), not the APP root. Verify with `/tmp/g7.py`.

- [ ] **Step 4: G-8 — thread-safety boundary.** In `docs/introduction/design-decisions.md` (near the existing concurrency note), document the boundary as it stands after the round-1 B-11 fix: cached (singleton) creation is guarded by a per-container reentrant lock; `ProvidersRegistry` mutations are now lock-guarded and iteration is snapshot-based, so concurrent registration is safe; but the intended usage remains "register all providers/groups before serving concurrent resolutions." `set_context`/overrides are last-write-wins. Verify claims against `registries/providers_registry.py` and `container.py`.

- [ ] **Step 5: `just lint-ci`** → clean (new page must pass eof-fixer). Run `/tmp/g6.py`, `/tmp/g7.py` → exit 0. Build-check the nav: `uv run --no-sync python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('mkdocs.yml').read_text())"` parses.

- [ ] **Step 6: Commit**

```bash
git add docs/providers/errors-and-exceptions.md docs/providers/lifecycle.md docs/providers/container.md docs/introduction/design-decisions.md mkdocs.yml
git commit -m "Docs: exception taxonomy page, close-failure semantics, container_provider scoping, thread-safety boundary (G-5, G-6, G-7, G-8)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 11: Docs — G-2, G-10, G-11 (reuse-after-close gap, advanced surface, mkdocs orphans)

**Files:**
- Modify: `docs/providers/lifecycle.md` (G-2 gap)
- Modify: `docs/providers/container.md` (G-10)
- Modify: `mkdocs.yml` (G-11)

- [ ] **Step 1: G-2 — finish the reuse-after-close gap.** Round-1 added a close/reopen subsection to `docs/providers/lifecycle.md` but did not state that resolving (or building a child) on a closed container *outside* a re-entered context manager raises `ContainerClosedError`. Add one sentence making the error case explicit (cross-reference the new exceptions page from G-5). Verify with `/tmp/g2.py` (resolve after close → `ContainerClosedError`).

- [ ] **Step 2: G-10 — advanced/extension surface.** In `docs/providers/container.md` add an "Advanced" subsection documenting the lower-level public surface, verified against source: `find_container(scope)`, the `parent_container` constructor kwarg (and that it enforces strict scope ordering — the round-1 B-6 check), `scope_map`, `lock`, `Group.get_providers()`, subclassing `AbstractProvider` (implement `resolve`; optional `get_dependencies`/`iter_validation_issues`; set `enforces_dependency_scope` — the Task-4 flag — if scope is decorative), and `CacheSettings.is_async_finalizer`. Keep it concise — a short definition per name. Verify each named attribute/method exists in source.

- [ ] **Step 3: G-11 — mkdocs orphan pages.** `docs/superpowers/` (specs + plans) sits inside `docs_dir: docs` with no nav entries, so it builds as orphan pages on the published site. Exclude it. Read `mkdocs.yml`; add an exclusion — preferred is the `exclude-search`/`exclude` plugin if already present, else set `not_in_nav` and/or use the `exclude` mkdocs option. Simplest robust approach: add to `mkdocs.yml`:

```yaml
exclude_docs: |
  superpowers/
```

(`exclude_docs` is built into mkdocs ≥1.5 and removes the files from the build entirely.) Verify with a build: `uvx --with-requirements docs/requirements.txt mkdocs build --strict --site-dir /tmp/site 2>&1 | tail -5` — confirm no `superpowers/` pages in `/tmp/site` and no orphan warnings. If `--strict` surfaces unrelated pre-existing warnings, build without `--strict` and just grep the site dir for `superpowers`.

- [ ] **Step 4: `just lint-ci`** → clean. Run `/tmp/g2.py` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add docs/providers/lifecycle.md docs/providers/container.md mkdocs.yml
git commit -m "Docs: reuse-after-close error case, advanced surface, exclude superpowers from site build (G-2, G-10, G-11)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 12: Final verification + report status

- [ ] **Step 1: Full gate.** `just lint-ci && just test-ci` → green, 100% coverage. `just bench` → 22 pass. Report the test count.

- [ ] **Step 2: Re-run all doc probes** written to `/tmp/` across Tasks 2/8/9/10/11 → all exit 0.

- [ ] **Step 3: Cross-version check (the round-1 lesson).** Run the suite on the strict interpreter too: `uv run --python 3.14 --with typing_extensions --with pytest-cov --with pytest-asyncio --with pytest-benchmark --with pytest-repeat pytest tests/ --cov=. --cov-fail-under=100 -p no:cacheprovider -q 2>&1 | tail -3` → green at 100%. **Important:** this may repoint the project `.venv` to 3.14 without deps; afterward run `uv sync --all-extras --frozen --group lint` to restore the 3.13 environment, then re-confirm `just test-ci` is green.

- [ ] **Step 4: Update the audit report status line.** In `planning/audits/2026-06-12-code-docs-audit-report.md`, extend the `**Status**` block: mark Q-1, Q-5, Q-6, Q-7, Q-8, Q-9, X-2, X-3, X-4, X-5, X-6, D-2, D-4, D-5, G-1, G-2, G-3, G-5, G-6, G-7, G-8, G-9, G-10, G-11 fixed on branch `audit-fixes-round2-2026-06-13`. Note the design rulings: Q-1/G-3 implemented None-injection; X-3 keeps resolving (documented); Q-6/X-6 moved coverage to recipes. After this round, the audit has no remaining deferred findings.

- [ ] **Step 5: Commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit report: mark round-2 findings fixed" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Then use superpowers:finishing-a-development-branch (PR, per the round-1 workflow).
