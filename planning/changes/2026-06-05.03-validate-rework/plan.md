---
status: shipped
date: 2026-06-05
slug: validate-rework
spec: design.md
pr: null
---

# `Container.validate()` Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework `Container.validate()` so it walks all scopes (the audit's must-fix-now #2), gains two new validation checks (inverted-scope deps and missing required deps), and accumulates all errors into a single `ValidationFailedError`.

**Architecture:** Refactor `Factory.get_dependencies` to be a pure dependency lookup (no `find_container`, no cache, no context check). Add a new `iter_validation_issues` method on `AbstractProvider` (default no-op) that `Factory` overrides to surface missing-dep issues. Rewrite `Container.validate()._visit` to accumulate cycles + scope-edge errors + per-provider validation issues, then raise an aggregate `ValidationFailedError` at the end if any.

**Tech Stack:** Python (the library); `pytest` for tests; `just lint-ci` (eof-fixer + ruff format + ruff check + ty check) for hygiene; `gh` for the PR.

---

## File structure

**Modified by this plan:**

- `modern_di/providers/abstract.py` — add `iter_validation_issues(container) -> Iterable[Exception]` with default `iter(())`.
- `modern_di/providers/factory.py` — add `_find_dep_provider` helper, refactor `_compile_kwargs` to use it, rewrite `get_dependencies` as a pure lookup, override `iter_validation_issues` to yield missing-dep `ArgumentResolutionError`s.
- `modern_di/exceptions.py` — add `InvalidScopeDependencyError` (subclass of `RegistrationError`) and `ValidationFailedError` (subclass of `ContainerError`).
- `modern_di/errors.py` — add one template constant `INVALID_SCOPE_DEPENDENCY_ERROR`.
- `modern_di/container.py` — rewrite `validate()` to accumulate errors and raise `ValidationFailedError` at the end.
- `tests/test_container.py` — update 2 existing tests for new exception shape, add 5 new tests.

**Created:** nothing.

**Spec reference:** `planning/specs/2026-06-05-validate-rework-design.md`. Read it before starting.

---

## Background — context the engineer needs

The current `Container.validate()` (`modern_di/container.py:109-133`) does cycle detection via DFS using `visited`/`visiting`/`path` sets. For each node it calls `provider.get_dependencies(self)`. The default `AbstractProvider.get_dependencies` returns `{}`; `Alias.get_dependencies` returns `{"source": provider}` using only `providers_registry`; `Factory.get_dependencies` (factory.py:131-135) calls `container.find_container(self.scope)` and uses the scoped `cache_registry` to memoize compiled kwargs. The `find_container` call is the bug: it raises `ScopeNotInitializedError` whenever the provider's scope is deeper than the container's, which makes `validate()` unusable on any graph with non-APP-scoped providers.

The fix is conceptually small: `get_dependencies` only needs the shared `providers_registry` (which exists on every container), not the scoped cache. Strip the find_container coupling, share the type→provider lookup with `_compile_kwargs` via a small `_find_dep_provider` helper, and `get_dependencies` becomes a pure static-graph operation.

While reworking the validate path, two more checks fit naturally:

- **Inverted scope:** an edge `provider → dep` where `dep.scope > provider.scope` is a wiring bug — at resolve time this manifests as `ScopeNotInitializedError` from `find_container`; at validate time we can name the offending edge directly.
- **Missing required dependency:** the same `ArgumentResolutionError` that `_compile_kwargs` raises at resolve time — raised earlier, at validate.

To avoid the "one error at a time" UX, `validate()` accumulates and raises a single aggregate `ValidationFailedError` containing all issues found, similar to how linters and test runners batch failures.

**Two existing tests change shape** (`test_validate_on_creation`, `test_validate_detects_cycle` in `test_container.py`): they currently catch `CircularDependencyError` directly; after the rework they catch `ValidationFailedError` and inspect `.errors[0]` for the inner cycle exception. This is intentional and is part of the API change.

**The cycle-detection bookkeeping has a subtle invariant the rewrite must preserve.** Currently `_visit` does `visiting.add(pid); path.append(provider); ...; path.pop(); visiting.discard(pid); visited.add(pid)`. When a cycle is detected the current code raises **before** `path.append`, so the cleanup at the end is not skipped. After the rework, cycle detection records the error and `return`s instead of raising. The `return` must occur **before** `path.append` and `visiting.add`, so the early return doesn't leave inconsistent bookkeeping.

---

## Task 1: Branch off main and add new exception classes

**Files:**
- Modify: `modern_di/exceptions.py`
- Modify: `modern_di/errors.py`

- [ ] **Step 1: Create the feature branch**

```bash
git -C /Users/kevinsmith/src/pypi/modern-di switch -c validate-cross-scope-and-accumulate
git -C /Users/kevinsmith/src/pypi/modern-di status
```

Expected: branch switched, working tree clean.

- [ ] **Step 2: Add the `INVALID_SCOPE_DEPENDENCY_ERROR` template**

Append to `modern_di/errors.py` (at the end of the file, after existing template constants):

```python
INVALID_SCOPE_DEPENDENCY_ERROR = (
    "Provider {provider_name} (scope {provider_scope}) declares parameter "
    "{parameter_name!r} typed as a provider of {dep_name} at deeper scope "
    "{dep_scope}. A provider cannot depend on a deeper-scoped provider."
)
```

- [ ] **Step 3: Add `InvalidScopeDependencyError` and `ValidationFailedError` to `exceptions.py`**

In `modern_di/exceptions.py`, after the existing `DuplicateProviderTypeError` class (line 179 in the current file — `RegistrationError` ends just past there), add:

```python
class InvalidScopeDependencyError(RegistrationError):
    __slots__ = ("dep_provider", "parameter_name", "provider")

    def __init__(
        self,
        *,
        provider: "AbstractProvider[typing.Any]",
        parameter_name: str,
        dep_provider: "AbstractProvider[typing.Any]",
    ) -> None:
        self.provider = provider
        self.parameter_name = parameter_name
        self.dep_provider = dep_provider
        provider_name = provider.bound_type.__name__ if provider.bound_type else repr(provider)
        dep_name = dep_provider.bound_type.__name__ if dep_provider.bound_type else repr(dep_provider)
        super().__init__(
            errors.INVALID_SCOPE_DEPENDENCY_ERROR.format(
                provider_name=provider_name,
                provider_scope=provider.scope.name,
                parameter_name=parameter_name,
                dep_name=dep_name,
                dep_scope=dep_provider.scope.name,
            )
        )
```

After `InvalidScopeDependencyError`, add `ValidationFailedError`. Place it under `ContainerError` rather than `RegistrationError` because it is raised by `Container.validate()`:

```python
class ValidationFailedError(ContainerError):
    __slots__ = ("errors",)

    def __init__(self, *, errors: list[Exception]) -> None:
        self.errors = errors
        kinds = ", ".join(sorted({type(e).__name__ for e in errors}))
        super().__init__(f"Container.validate() found {len(errors)} issue(s): {kinds}")

    def __str__(self) -> str:
        header = super().__str__()
        rendered = "\n".join(f"  - {e}" for e in self.errors)
        return f"{header}\n{rendered}"
```

Note the forward-reference annotation `"AbstractProvider[typing.Any]"` — `AbstractProvider` is not imported in `exceptions.py` today. Add to the existing `if typing.TYPE_CHECKING:` block (or create one if absent) at the top of `exceptions.py`:

```python
if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider
```

`typing` is already imported in `exceptions.py`.

- [ ] **Step 4: Verify the existing suite is still green**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 126 passed (or whatever the current count is on `main`). The new exception classes are unused so nothing should change behavior.

- [ ] **Step 5: Do NOT commit yet**

Subsequent tasks build on this. The final atomic commit happens in Task 6.

---

## Task 2: Add `iter_validation_issues` default to `AbstractProvider`

**Files:**
- Modify: `modern_di/providers/abstract.py`

- [ ] **Step 1: Add the method**

In `modern_di/providers/abstract.py`, after the existing `get_dependencies` method (lines 31-32 in the current file), add:

```python
    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
        """Yield validation-time issues for this provider. Default: no issues."""
        return iter(())
```

`typing` is already imported.

- [ ] **Step 2: Verify existing suite still green**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: same green count. The new method has no callers yet.

- [ ] **Step 3: Do NOT commit**

---

## Task 3: Extract `_find_dep_provider` in `Factory`, refactor `_compile_kwargs`

**Files:**
- Modify: `modern_di/providers/factory.py`

- [ ] **Step 1: Add the helper method**

In `modern_di/providers/factory.py`, just before `_compile_kwargs` (which starts at line 68 in the current file), add this method:

```python
    def _find_dep_provider(
        self, container: "Container", v: SignatureItem
    ) -> "AbstractProvider[typing.Any] | None":
        if v.arg_type:
            provider = container.providers_registry.find_provider(v.arg_type)
            if provider is self:
                return None
            return provider
        for x in v.args:
            provider = container.providers_registry.find_provider(x)
            if provider:
                return provider
        return None
```

- [ ] **Step 2: Refactor `_compile_kwargs` to use the helper**

Replace the body of `_compile_kwargs` (lines 68-112 in current file) with this. The runtime behavior — error raising, context-value check — is preserved exactly:

```python
    def _compile_kwargs(self, container: "Container") -> dict[str, typing.Any]:
        result: dict[str, typing.Any] = {}
        for k, v in self._parsed_kwargs.items():
            provider = self._find_dep_provider(container, v)
            is_kwarg_not_found = not self._kwargs or k not in self._kwargs
            if provider:
                result[k] = provider
                if (
                    is_kwarg_not_found
                    and isinstance(provider, ContextProvider)
                    and provider._find_context_value(container) is types.UNSET  # noqa: SLF001
                ):
                    raise exceptions.ArgumentResolutionError(
                        arg_name=k, arg_type=v.arg_type, bound_type=self.bound_type or self._creator
                    )
                continue

            if v.default == types.UNSET and is_kwarg_not_found:
                suggestions = (
                    container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
                )
                raise exceptions.ArgumentResolutionError(
                    arg_name=k,
                    arg_type=v.arg_type,
                    bound_type=self.bound_type or self._creator,
                    suggestions=suggestions,
                )

        if self._kwargs:
            result.update(self._kwargs)
        return result
```

- [ ] **Step 3: Verify suite still green — _compile_kwargs is exercised heavily by `test_factory.py`**

```bash
uv run pytest tests/providers/test_factory.py -v 2>&1 | tail -10
uv run pytest 2>&1 | tail -3
```

Expected: all factory tests pass; full suite still 126 passed. This is a pure refactor — the helper replaced inline code with the same semantics.

- [ ] **Step 4: Do NOT commit**

---

## Task 4: Rewrite `Factory.get_dependencies` and add `Factory.iter_validation_issues`

**Files:**
- Modify: `modern_di/providers/factory.py`

- [ ] **Step 1: Replace `Factory.get_dependencies`**

Replace the existing `get_dependencies` method (lines 131-135 in the current file) with:

```python
    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        """Return parameter-name → dependency-provider mapping using only the providers registry.

        Pure lookup: no scope check, no cache touch, no context-value lookup. Used by
        Container.validate() to traverse the static graph.
        """
        result: dict[str, AbstractProvider[typing.Any]] = {}
        for k, v in self._parsed_kwargs.items():
            if self._kwargs and k in self._kwargs:
                continue
            provider = self._find_dep_provider(container, v)
            if provider is not None:
                result[k] = provider
        return result
```

- [ ] **Step 2: Add `iter_validation_issues` to `Factory`**

Place it right after `get_dependencies`:

```python
    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:
        """Yield ArgumentResolutionError for parameters with no provider, no default, no static kwarg."""
        for k, v in self._parsed_kwargs.items():
            is_kwarg_not_found = not self._kwargs or k not in self._kwargs
            if not is_kwarg_not_found:
                continue
            if self._find_dep_provider(container, v) is not None:
                continue
            if v.default is not types.UNSET:
                continue
            suggestions = (
                container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
            )
            yield exceptions.ArgumentResolutionError(
                arg_name=k,
                arg_type=v.arg_type,
                bound_type=self.bound_type or self._creator,
                suggestions=suggestions,
            )
```

- [ ] **Step 3: Verify existing suite still green**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 126 passed. Even with the new `get_dependencies` behavior, existing tests pass because:
- All existing validate tests use APP-scoped providers; the new pure lookup produces identical results to the old behavior for APP-only graphs.
- `test_validate_memoizes_diamond` patches `get_dependencies` on a Factory instance; the patch still works (instance attribute beats class method).
- `Factory.resolve` still uses `_ensure_kwargs_cached` via its own scoped path; that's unchanged.

- [ ] **Step 4: Do NOT commit**

---

## Task 5: Update existing tests and add 5 new tests (TDD red)

**Files:**
- Modify: `tests/test_container.py`

- [ ] **Step 1: Confirm necessary imports are present**

Open `tests/test_container.py`. Confirm these are imported at the top (most should be already):

```python
import dataclasses
import typing
import pytest
from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import (
    CircularDependencyError,
    ArgumentResolutionError,
    InvalidScopeDependencyError,
    ValidationFailedError,
)
from modern_di.providers.abstract import AbstractProvider
```

If any are missing, add them. `InvalidScopeDependencyError` and `ValidationFailedError` were just added in Task 1 — confirm the import resolves.

- [ ] **Step 2: Replace `test_validate_on_creation`**

Find the existing `test_validate_on_creation` (around line 104) and replace its body:

```python
def test_validate_on_creation() -> None:
    with pytest.raises(ValidationFailedError) as exc:
        Container(groups=[CycleGroup], validate=True)
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)
```

- [ ] **Step 3: Replace `test_validate_detects_cycle`**

Find the existing `test_validate_detects_cycle` (around line 109) and replace its body:

```python
def test_validate_detects_cycle() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)
    assert issue.cycle_path == ["CycleA", "CycleB", "CycleA"]
```

- [ ] **Step 4: Append the 5 new tests**

Append at the end of the file:

```python
def test_validate_walks_deeper_scoped_providers() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        pass

    class G(Group):
        svc = providers.Factory(scope=Scope.REQUEST, creator=Service)

    Container(groups=[G], validate=True)


def test_validate_raises_on_inverted_scope_dependency() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner

    class G(Group):
        inner = providers.Factory(scope=Scope.REQUEST, creator=Inner)
        outer = providers.Factory(scope=Scope.APP, creator=Outer)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, InvalidScopeDependencyError)
    assert issue.parameter_name == "inner"
    assert issue.provider.scope == Scope.APP
    assert issue.dep_provider.scope == Scope.REQUEST


def test_validate_raises_on_missing_required_dependency() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        missing: Missing

    class G(Group):
        svc = providers.Factory(creator=Service)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)
    assert issue.arg_name == "missing"


def test_validate_accumulates_multiple_errors() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Bad:
        missing: Missing

    class CycleX:
        def __init__(self, y: "CycleY") -> None: ...

    class CycleY:
        def __init__(self, x: CycleX) -> None: ...

    class G(Group):
        inner = providers.Factory(scope=Scope.REQUEST, creator=Inner)
        outer = providers.Factory(scope=Scope.APP, creator=Outer)
        bad = providers.Factory(creator=Bad)
        cycle_x = providers.Factory(creator=CycleX)
        cycle_y = providers.Factory(creator=CycleY)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    error_types = {type(e) for e in exc.value.errors}
    assert InvalidScopeDependencyError in error_types
    assert ArgumentResolutionError in error_types
    assert CircularDependencyError in error_types
    assert len(exc.value.errors) >= 3


def test_validate_detects_cycle_across_scopes() -> None:
    class A:
        def __init__(self, b: "B") -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    class G(Group):
        a = providers.Factory(scope=Scope.REQUEST, creator=A)
        b = providers.Factory(scope=Scope.REQUEST, creator=B)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)
```

- [ ] **Step 5: Run new + updated tests, observe failures**

```bash
uv run pytest tests/test_container.py -v --no-cov 2>&1 | tail -30
```

Expected:
- `test_validate_walks_deeper_scoped_providers` — **PASS** (Task 4's get_dependencies fix is sufficient for this one; the other validate tests would also pass through validate without raising).
- `test_validate_on_creation` — **FAIL** with `CircularDependencyError` instead of `ValidationFailedError`.
- `test_validate_detects_cycle` — **FAIL** for the same reason.
- `test_validate_raises_on_inverted_scope_dependency` — **FAIL** with `DID NOT RAISE` (validate succeeds because the scope check doesn't exist yet).
- `test_validate_raises_on_missing_required_dependency` — **FAIL** with `DID NOT RAISE`.
- `test_validate_accumulates_multiple_errors` — **FAIL** with `CircularDependencyError` (validate stops at first cycle without accumulating).
- `test_validate_detects_cycle_across_scopes` — **FAIL** with `CircularDependencyError` instead of `ValidationFailedError`.

This is TDD red. The next task makes them all green.

- [ ] **Step 6: Do NOT commit (tests fail)**

---

## Task 6: Rewrite `Container.validate()` to accumulate, then atomic commit

**Files:**
- Modify: `modern_di/container.py`

- [ ] **Step 1: Replace `Container.validate()`**

In `modern_di/container.py`, replace the entire body of the `validate` method (lines 109-133 in the current file) with:

```python
    def validate(self) -> None:
        validation_errors: list[Exception] = []
        visiting: set[int] = set()
        visited: set[int] = set()
        path: list[AbstractProvider[typing.Any]] = []

        def _visit(provider: AbstractProvider[typing.Any]) -> None:
            pid = provider.provider_id
            if pid in visited:
                return
            if pid in visiting:
                cycle_start = next(i for i, p in enumerate(path) if p.provider_id == pid)
                cycle_names = [p.bound_type.__name__ if p.bound_type else repr(p) for p in path[cycle_start:]]
                cycle_names.append(cycle_names[0])
                validation_errors.append(exceptions.CircularDependencyError(cycle_path=cycle_names))
                return  # cycle recorded; do not recurse or touch bookkeeping

            visiting.add(pid)
            path.append(provider)
            validation_errors.extend(provider.iter_validation_issues(self))

            for dep_name, dep_provider in provider.get_dependencies(self).items():
                if dep_provider.scope > provider.scope:
                    validation_errors.append(
                        exceptions.InvalidScopeDependencyError(
                            provider=provider,
                            parameter_name=dep_name,
                            dep_provider=dep_provider,
                        )
                    )
                _visit(dep_provider)

            path.pop()
            visiting.discard(pid)
            visited.add(pid)

        for one_provider in self.providers_registry:
            _visit(one_provider)

        if validation_errors:
            raise exceptions.ValidationFailedError(errors=validation_errors)
```

Note the use of `validation_errors` (not `errors`) for the local list — `errors` is a module alias for `modern_di.errors` imported elsewhere in the file. Using a distinct name avoids shadowing.

Note the cycle-detection bookkeeping invariant: the cycle branch returns **before** touching `visiting` or `path`, so the early return doesn't corrupt the DFS state. The outer entry that owns this `pid` cleans up in its own `_visit` frame on the way out.

- [ ] **Step 2: Run new + updated tests, expect all pass**

```bash
uv run pytest tests/test_container.py -v --no-cov 2>&1 | tail -25
```

Expected: all 7 affected tests pass (5 new + 2 updated), plus the rest of `test_container.py`. If a test fails, inspect the failure and fix before continuing — do not commit broken tests.

- [ ] **Step 3: Run full suite, expect all pass**

```bash
uv run pytest 2>&1 | tail -5
```

Expected: full suite green, 131 passed (previously 126; we added 5 tests). 100% coverage maintained.

If a test in `test_factory.py` or `test_singleton.py` regressed, the most likely cause is the `_compile_kwargs` refactor in Task 3 — re-check that the refactored loop preserves the original semantics. The new `get_dependencies` should NOT affect resolve-time tests because resolve uses `_ensure_kwargs_cached` directly, not `get_dependencies`.

- [ ] **Step 4: Lint and type-check**

```bash
just lint-ci
```

Expected: clean — eof-fixer, ruff format --check, ruff check, ty check. If `ruff format` flags new code, run `uv run ruff format .` to auto-fix and re-run `just lint-ci`.

- [ ] **Step 5: Atomic commit**

```bash
git -C /Users/kevinsmith/src/pypi/modern-di add \
  modern_di/container.py \
  modern_di/exceptions.py \
  modern_di/errors.py \
  modern_di/providers/abstract.py \
  modern_di/providers/factory.py \
  tests/test_container.py
git -C /Users/kevinsmith/src/pypi/modern-di commit -m "Rework Container.validate() to walk all scopes, check inverted-scope deps, accumulate errors"
git -C /Users/kevinsmith/src/pypi/modern-di log --oneline -1
```

Expected: one commit with the exact subject above. Six files staged and committed atomically.

---

## Task 7: Push branch and open PR

- [ ] **Step 1: Push the branch**

```bash
git -C /Users/kevinsmith/src/pypi/modern-di push -u origin validate-cross-scope-and-accumulate
```

Expected: branch created on `origin`, tracking set.

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "Rework Container.validate() to walk all scopes, check inverted-scope deps, accumulate errors" --body "$(cat <<'EOF'
## Summary
- `Container.validate()` was unusable on any DI graph with non-APP-scoped providers: `Factory.get_dependencies` called `container.find_container(self.scope)` and raised `ScopeNotInitializedError` before validation could complete. The documented `validate=True` startup check was therefore broken for its real audience (apps with `REQUEST` / `SESSION` / `ACTION` / `STEP`-scoped providers).
- This change refactors `Factory.get_dependencies` to a pure type→provider lookup (no `find_container`, no `cache_registry`, no context-value check), sharing a `_find_dep_provider` helper with `_compile_kwargs`. `Factory.resolve` is unaffected.
- While reworking the validate path, two more wiring-bug classes are now caught at validate time instead of at first `resolve()`: **inverted scope dependencies** (a provider depending on another with a strictly deeper scope) and **missing required dependencies** (a parameter with no provider, no default, no static kwarg).
- All validation errors are accumulated and raised together as a single \`ValidationFailedError\` with an \`.errors: list[Exception]\` attribute. Single-error-then-stop was the wrong UX for a wiring audit. Two existing cycle tests change shape to catch the aggregate; documented in the spec.

Surfaced by the 2026-06-05 bug-hunt audit (\`planning/audits/2026-06-05-bug-hunt-audit-report.md\`, must-fix-now #2). Design: \`planning/specs/2026-06-05-validate-rework-design.md\`. Plan: \`planning/plans/2026-06-05-validate-rework-plan.md\`.

## Changes
- \`modern_di/providers/abstract.py\`: add \`iter_validation_issues\` with default no-op.
- \`modern_di/providers/factory.py\`: add \`_find_dep_provider\` helper; refactor \`_compile_kwargs\` to use it (no behavior change); rewrite \`get_dependencies\` as pure lookup; override \`iter_validation_issues\` to yield missing-dep \`ArgumentResolutionError\`s.
- \`modern_di/exceptions.py\`: add \`InvalidScopeDependencyError\` (under \`RegistrationError\`) and \`ValidationFailedError\` (under \`ContainerError\`).
- \`modern_di/errors.py\`: add \`INVALID_SCOPE_DEPENDENCY_ERROR\` template.
- \`modern_di/container.py\`: rewrite \`Container.validate()\` to accumulate cycles + scope-edge errors + per-provider issues; raise \`ValidationFailedError\` at end.
- \`tests/test_container.py\`: update 2 existing tests for new aggregate shape; add 5 new tests covering deeper-scoped, inverted-scope, missing-dep, multi-error accumulation, and cross-scope cycle.

## Test plan
- [x] 5 new tests pass locally.
- [x] 2 updated tests pass (\`test_validate_on_creation\`, \`test_validate_detects_cycle\`).
- [x] \`test_validate_passes_for_valid_graph\` and \`test_validate_memoizes_diamond\` still pass unchanged.
- [x] Full suite (\`uv run pytest\`) green, 100% coverage maintained.
- [x] \`just lint-ci\` green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: `gh` returns the PR URL. Report the URL.

- [ ] **Step 3: Confirm CI is running**

```bash
gh pr checks --watch
```

Expected: CI kicks off. Either watch the checks complete or stop here and let CI run in the background.

---

## Self-review

**Spec coverage check:**

- Goal #1 (validate works on non-APP-scoped providers) — Task 4 (get_dependencies rewrite) + Task 5 step 4 (test_validate_walks_deeper_scoped_providers).
- Goal #2 (inverted-scope check) — Task 6 (validate's `_visit` adds the scope edge check) + Task 5 (test_validate_raises_on_inverted_scope_dependency).
- Goal #3 (missing-dep check) — Task 4 (Factory.iter_validation_issues) + Task 6 (validate calls it) + Task 5 (test_validate_raises_on_missing_required_dependency).
- Goal #4 (accumulate) — Task 6 (validate accumulates to list, raises ValidationFailedError at end) + Task 5 (test_validate_accumulates_multiple_errors).
- Scope #1 (refactor get_dependencies as pure lookup) — Task 4.
- Scope #2 (iter_validation_issues method) — Task 2 (default) + Task 4 (Factory override).
- Scope #3 (rewrite validate to accumulate) — Task 6.
- Scope #4 (InvalidScopeDependencyError, ValidationFailedError) — Task 1.
- Scope #5 (INVALID_SCOPE_DEPENDENCY_ERROR template) — Task 1 step 2.
- Scope #6 (7 tests: 5 new + 2 updated) — Task 5.
- Non-goals (Factory.resolve unchanged, Alias/ContextProvider/container_provider unchanged, no docs work) — preserved by construction; no task touches those files.
- Sequencing (12 steps in spec) — distributed across Tasks 1-7.
- Risks (cycle-detection bookkeeping invariant) — Task 6 Step 1 calls it out explicitly.

**Placeholder scan:** none. Every code block is the actual code; every command is the actual command.

**Type / name consistency:** `ValidationFailedError`, `InvalidScopeDependencyError`, `iter_validation_issues`, `_find_dep_provider`, `validation_errors`, `dep_provider`, `parameter_name`, `provider_name`, `dep_name` — all match between definition sites and call sites across tasks. Branch name `validate-cross-scope-and-accumulate` and commit subject identical between Task 6 and Task 7. PR title same as commit subject.

**Sequencing sanity:**
- Tasks 1-4 set up the infrastructure without changing observable behavior of any existing test (existing tests still green after each task).
- Task 5 introduces failing tests (TDD red).
- Task 6 rewrites validate (TDD green) and commits atomically — all setup + tests + final implementation in one commit, matching the project's commit style.
- Task 7 ships the branch.

No task is reorderable without breaking either TDD discipline or atomic-commit hygiene.
