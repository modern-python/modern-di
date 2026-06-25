---
summary: Reworked validate() for transitive cycle/scope checks; shipped in 2.15.0.
---

# `Container.validate()` Rework — Design

**Date:** 2026-06-05
**Status:** Draft, pending user approval
**Source:** `planning/audits/2026-06-05-bug-hunt-audit-report.md`, `must-fix-now` finding "`validate=True` raises `ScopeNotInitializedError` for any provider whose scope is deeper than the root container"

## Goal

Fix `Container.validate()` so it works on real-world DI graphs (non-APP-scoped providers), and while reworking the dependency-discovery path, expand `validate()` to catch two more wiring-bug classes that today only surface at the first call to `resolve()`:

1. **Inverted scope dependency** — a provider depending on another with a strictly deeper scope (e.g., APP depending on REQUEST). Caught at startup instead of at first request.
2. **Missing required dependency** — a parameter has no matching provider, no default, no static kwarg. Same `ArgumentResolutionError` raised earlier.

Accumulate all errors across the walk and raise a single aggregate `ValidationFailedError` at the end. Single-error-then-stop is the wrong UX for a wiring audit; users want to see every issue at once, the way linters and test runners batch failures.

## Background

The audit's second `must-fix-now` finding (`planning/audits/2026-06-05-bug-hunt-audit-report.md`) documents that `Container.validate()` calls `provider.get_dependencies(self)` (where `self` is the root container), and `Factory.get_dependencies` calls `container.find_container(self.scope)` — which raises `ScopeNotInitializedError` for any provider scoped deeper than the root. Consequently, calling `validate()` (or constructing with `validate=True`) blows up the moment any provider has scope `REQUEST` / `SESSION` / `ACTION` / `STEP` — the typical case for any non-toy app. The feature is broken for its real audience, with a confusing error.

Today `validate()` is documented as cycle detection. The only caller of `get_dependencies` in the codebase is `Container.validate()._visit` at `modern_di/container.py:126`. The find_container call in `Factory.get_dependencies` is incidental — used to memoize kwargs compilation on the scoped `cache_registry`, an optimization for the resolve path. Validate doesn't need it; the dependency lookup itself only needs the shared `providers_registry`, which exists on every container in the tree.

Existing tests (`tests/test_container.py:104-172`) all use the default APP scope, which is why CI is green: the bug is invisible to the current test suite.

While we're rewiring `get_dependencies`, two other validate-time checks are cheap to add and meaningfully improve the feature:

- **Scope correctness** — for each edge `provider → dep`, `dep.scope > provider.scope` is a wiring bug (a shallower-scoped provider cannot hold a deeper-scoped instance). At resolve time, this manifests as `ScopeNotInitializedError`. At validate time, we can name the offending edge directly.
- **Missing dependency** — `Factory._compile_kwargs` already raises `ArgumentResolutionError` at resolve time when a parameter has no matching provider, no default, and no static kwarg. The same check fits naturally into validate.

## Scope

### In scope

- **Refactor `Factory.get_dependencies`** to be a pure dependency lookup. No `find_container`, no `cache_registry`, no `_find_context_value` check (all runtime concerns). Extract a `_find_dep_provider(container, v)` helper used by both `get_dependencies` and `_compile_kwargs` so the type→provider lookup logic is shared.
- **Add `iter_validation_issues(container) -> Iterable[Exception]`** on `AbstractProvider`. Default implementation returns an empty iterator. `Factory` overrides to yield `ArgumentResolutionError` instances for parameters with no provider, no default, no static kwarg. Other providers (Alias, ContextProvider, container_provider) keep the default.
- **Rewrite `Container.validate()`** to accumulate errors:
  - Each cycle encountered during DFS is recorded as a `CircularDependencyError`; the recursion stops at the cycle (don't loop) but other branches continue.
  - For each edge `provider → dep`, check `dep.scope > provider.scope` and record an `InvalidScopeDependencyError` if so. Recurse anyway — the dep may have further issues worth surfacing.
  - For each provider entered during DFS, extend the error list with `list(provider.iter_validation_issues(self))`.
  - At the end, if any errors collected, raise `ValidationFailedError(errors=[...])`. Otherwise return None.
- **Add `InvalidScopeDependencyError`** in `modern_di/exceptions.py` (subclass of `RegistrationError`) with a template in `modern_di/errors.py`. Fields: `provider`, `parameter_name`, `dep_provider`.
- **Add `ValidationFailedError`** in `modern_di/exceptions.py` (subclass of `ContainerError`, since `Container.validate` raises it). Fields: `errors: list[Exception]`. Message: short summary of count + types, full per-error rendering when `__str__` is called.
- **Tests** in `tests/test_container.py`:
  - Update two existing tests (`test_validate_on_creation`, `test_validate_detects_cycle`) to match the new aggregate exception shape: `pytest.raises(ValidationFailedError) as exc` then assert `isinstance(exc.value.errors[0], CircularDependencyError)` and inspect `.cycle_path` on the inner.
  - Update `test_validate_passes_for_valid_graph` and `test_validate_memoizes_diamond` to keep passing — they should not need changes, but verify.
  - Add `test_validate_walks_deeper_scoped_providers` — REQUEST-scoped Factory under an APP container; validate passes. Today this raises `ScopeNotInitializedError`.
  - Add `test_validate_raises_on_inverted_scope_dependency` — APP-scoped provider depends on a REQUEST-scoped one. Validate raises `ValidationFailedError` with one `InvalidScopeDependencyError`.
  - Add `test_validate_raises_on_missing_required_dependency` — Factory whose creator has a parameter with no matching provider, no default, no static kwarg. Validate raises `ValidationFailedError` with one `ArgumentResolutionError`.
  - Add `test_validate_accumulates_multiple_errors` — graph with one cycle AND one inverted-scope dep AND one missing dep. Validate raises `ValidationFailedError` with all three `.errors`. This is the key accumulation test.
  - Add `test_validate_detects_cycle_across_scopes` — cycle that spans APP and REQUEST scopes. Cycle is still detected.
- One commit, one feature branch, one PR.

### Non-goals

- **`Factory.resolve` behavior unchanged.** Same code path, same lock acquisition (or with the prior `use-rlock-for-reentrant-resolution` PR merged, same RLock). The `_find_dep_provider` extraction is purely internal.
- **Alias, ContextProvider, container_provider implementations unchanged.** Their `get_dependencies` already works in validate (no `find_container` call). Their `iter_validation_issues` uses the default empty implementation.
- **`validate()` algorithm core unchanged** — still DFS with `visiting` / `visited` / `path` sets. Only the per-node body changes (error accumulation, scope edge check).
- **No async `validate()`, no parallel `validate()`, no caching across calls.**
- **No `validate()` performance work.** The graph is small for any realistic project; correctness first.
- **No documentation rewrites in `docs/` or `CLAUDE.md` beyond what falls out from the diff.** README and CLAUDE.md describe `validate` as cycle detection; the rework expands that, but the docs claim "cycle detection on the provider graph at container creation time" remains broadly accurate. If a docstring on `Container.validate` exists, update it; otherwise out of scope.

## Success criteria

1. New regression tests, written first against current `main`, exercise the bugs:
   - `test_validate_walks_deeper_scoped_providers` raises `ScopeNotInitializedError` on `main`, passes after fix.
   - `test_validate_raises_on_inverted_scope_dependency`, `test_validate_raises_on_missing_required_dependency`, `test_validate_accumulates_multiple_errors`, `test_validate_detects_cycle_across_scopes` fail on `main` (most because the validate call itself raises `ScopeNotInitializedError` before reaching the actual check; some because the check doesn't exist yet).
2. After the fix, all new tests pass.
3. Updated existing tests (`test_validate_on_creation`, `test_validate_detects_cycle`) pass with new exception shape.
4. Other existing tests (`test_validate_passes_for_valid_graph`, `test_validate_memoizes_diamond`, all of `test_factory.py`, `test_singleton.py`, etc.) continue to pass unchanged.
5. `just lint-ci` (eof-fixer + ruff format + ruff check + ty check) clean.
6. Full coverage maintained.

## The change

### `modern_di/providers/abstract.py`

Add the new method with default empty iterator implementation.

```python
def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
    """Yield validation-time issues for this provider. Default: no issues."""
    return iter(())
```

(Imports: `typing` is already imported.)

### `modern_di/providers/factory.py`

Extract the type→provider lookup helper, rewrite `get_dependencies`, override `iter_validation_issues`, refactor `_compile_kwargs` to use the helper. Approximate shape:

```python
def _find_dep_provider(
    self, container: "Container", v: SignatureItem
) -> "AbstractProvider[typing.Any] | None":
    """Find a provider for a single parsed parameter, ignoring runtime concerns."""
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

def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
    """Return parameter-name → dependency-provider mapping using only the providers registry.

    Pure lookup: no scope check, no cache touch, no context-value lookup. Used by
    Container.validate() to traverse the static graph.
    """
    result: dict[str, AbstractProvider[typing.Any]] = {}
    for k, v in self._parsed_kwargs.items():
        if self._kwargs and k in self._kwargs:
            continue  # parameter satisfied by a static kwarg
        provider = self._find_dep_provider(container, v)
        if provider is not None:
            result[k] = provider
    return result

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

`_compile_kwargs` is refactored to use `_find_dep_provider` for the lookup step but keep its existing runtime-error behavior (context-value UNSET check, missing-dep raise at resolve time). Tests covering `_compile_kwargs` (in `tests/providers/test_factory.py`) should continue to pass unchanged.

### `modern_di/container.py`

Rewrite `validate()` to accumulate. Approximate shape:

```python
def validate(self) -> None:
    errors: list[Exception] = []
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
            errors.append(exceptions.CircularDependencyError(cycle_path=cycle_names))
            return  # cycle recorded; don't recurse into it

        visiting.add(pid)
        path.append(provider)
        errors.extend(provider.iter_validation_issues(self))

        for dep_name, dep_provider in provider.get_dependencies(self).items():
            if dep_provider.scope > provider.scope:
                errors.append(
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

    if errors:
        raise exceptions.ValidationFailedError(errors=errors)
```

### `modern_di/exceptions.py`

Add two new classes:

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


class ValidationFailedError(ContainerError):
    __slots__ = ("errors",)

    def __init__(self, *, errors: list[Exception]) -> None:
        self.errors = errors
        kinds = ", ".join(sorted({type(e).__name__ for e in errors}))
        super().__init__(
            f"Container.validate() found {len(errors)} issue(s): {kinds}"
        )

    def __str__(self) -> str:
        header = super().__str__()
        rendered = "\n".join(f"  - {e}" for e in self.errors)
        return f"{header}\n{rendered}"
```

The naming logic (`provider.bound_type.__name__ if provider.bound_type else repr(provider)`) is inlined in `InvalidScopeDependencyError.__init__` rather than extracted to a helper — mirrors the same inline pattern already used in `Container.validate()._visit` to name cycle members.

The forward reference to `AbstractProvider` requires a `TYPE_CHECKING` import or string annotations; pattern matches the existing code.

### `modern_di/errors.py`

Add one new template constant:

```python
INVALID_SCOPE_DEPENDENCY_ERROR = (
    "Provider {provider_name} (scope {provider_scope}) declares parameter "
    "{parameter_name!r} typed as a provider of {dep_name} at deeper scope "
    "{dep_scope}. A provider cannot depend on a deeper-scoped provider."
)
```

`ValidationFailedError` does not need a template constant — its message is composed inline in `__init__` / `__str__`.

## Test design

All new tests live in `tests/test_container.py`, near the existing `test_validate_*` family.

### `test_validate_walks_deeper_scoped_providers`

```python
def test_validate_walks_deeper_scoped_providers() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        pass

    class G(Group):
        svc = providers.Factory(scope=Scope.REQUEST, creator=Service)

    # Before fix: raises ScopeNotInitializedError.
    # After fix: returns silently.
    Container(groups=[G], validate=True)
```

### `test_validate_raises_on_inverted_scope_dependency`

```python
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
```

### `test_validate_raises_on_missing_required_dependency`

```python
def test_validate_raises_on_missing_required_dependency() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        missing: Missing

    class G(Group):
        svc = providers.Factory(creator=Service)
        # `Missing` is intentionally not registered.

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)
    assert issue.arg_name == "missing"
```

### `test_validate_accumulates_multiple_errors`

```python
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

    class CycleA:
        def __init__(self, b: "CycleB") -> None: ...

    class CycleB:
        def __init__(self, a: CycleA) -> None: ...

    class G(Group):
        inner = providers.Factory(scope=Scope.REQUEST, creator=Inner)
        outer = providers.Factory(scope=Scope.APP, creator=Outer)  # inverted scope
        bad = providers.Factory(creator=Bad)                       # missing dep
        cycle_a = providers.Factory(creator=CycleA)                # cycle
        cycle_b = providers.Factory(creator=CycleB)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    error_types = {type(e) for e in exc.value.errors}
    assert InvalidScopeDependencyError in error_types
    assert ArgumentResolutionError in error_types
    assert CircularDependencyError in error_types
    assert len(exc.value.errors) >= 3
```

### `test_validate_detects_cycle_across_scopes`

```python
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

### Updates to existing tests

In `tests/test_container.py`:

```python
def test_validate_on_creation() -> None:
    with pytest.raises(ValidationFailedError) as exc:
        Container(groups=[CycleGroup], validate=True)
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)


def test_validate_detects_cycle() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)
    assert issue.cycle_path == ["CycleA", "CycleB", "CycleA"]
```

`test_validate_passes_for_valid_graph` and `test_validate_memoizes_diamond` should not need changes — verify during execution.

## Branch, commit, PR conventions

Match patterns visible in `git log --oneline`:

- **Branch name:** `validate-cross-scope-and-accumulate`.
- **Commit message:** `Rework Container.validate() to walk all scopes, check inverted-scope deps, accumulate errors`. Imperative present-tense, describes the new behavior. Mirrors recent style like `Raise on async finalizer in close_sync; drop Group.providers cache; add __slots__ to exceptions`.
- **PR:** opened via `gh pr create` targeting `main`. Title same as the commit subject. Body cites the audit report path, the spec path, the design summary, and a test plan checklist.

## Sequencing

1. Branch off current `main`.
2. Add `iter_validation_issues` to `AbstractProvider` (no-op default).
3. Add `_find_dep_provider` helper in `Factory`, refactor `_compile_kwargs` to use it. Tests must still pass.
4. Rewrite `Factory.get_dependencies` (pure lookup) and add `Factory.iter_validation_issues`. Existing tests must still pass.
5. Add `InvalidScopeDependencyError` and `ValidationFailedError` to `exceptions.py`, plus the `INVALID_SCOPE_DEPENDENCY_ERROR` template in `errors.py`.
6. Write all new and updated tests in `tests/test_container.py`. Run them; expect:
   - `test_validate_walks_deeper_scoped_providers` and `test_validate_detects_cycle_across_scopes`: fail (or pass, depending on which intermediate step we're at).
   - `test_validate_on_creation` and `test_validate_detects_cycle`: fail because they expect the new aggregate exception that doesn't exist yet.
7. Rewrite `Container.validate()` to accumulate, raise `ValidationFailedError`.
8. Run the full suite — every test should pass now.
9. `just lint-ci` — clean.
10. Single commit. (Optional split into 2-3 commits per logical step if the reviewer benefits.)
11. `git push -u origin validate-cross-scope-and-accumulate`.
12. `gh pr create` with audit-cited body.

## Risks

- **Test churn for existing cycle tests.** `test_validate_on_creation` and `test_validate_detects_cycle` change shape (catch `ValidationFailedError` then inspect `.errors`). Two tests, ~6 lines each. Documented in the spec; reviewer expectation set.
- **`ValidationFailedError.__str__` rendering.** The aggregate's `__str__` joins per-error renderings with newlines. Long graphs may produce long messages; reasonable for a startup-time validation failure. Acceptable.
- **`InvalidScopeDependencyError` base class choice (RegistrationError).** Defensible — it's a static graph mis-declaration. Could be argued either way; documented as a choice rather than asserting one canonical answer.
- **Naming logic for providers in `InvalidScopeDependencyError` messages.** Inlined in the exception's `__init__`, mirrors the same inline pattern already in `Container.validate()._visit`. No new abstraction.
- **`iter_validation_issues` API surface.** Adds one method to `AbstractProvider`. Default no-op means downstream `AbstractProvider` subclasses (if any exist outside this repo) keep working unchanged.
- **Cycle detection with the `path` set during accumulation.** When a cycle is recorded, we `return` without recursing (don't loop), but we DO `path.pop()` and `visiting.discard(pid)` on the way out. Wait — actually, on cycle detection, the current code `return`s before `path.append(provider)` would matter (the cycle node was added to path on the FIRST entry; the recursive entry is the one that detects the cycle and returns without appending again). Need to double-check this in implementation: the `return` after recording the cycle must NOT pop `path` or remove from `visiting`, because the original entry still owns those. The plan should make this explicit.

## Deliverables

- **This spec:** `planning/specs/2026-06-05-validate-rework-design.md`.
- **Implementation plan (next phase, via writing-plans):** `planning/plans/2026-06-05-validate-rework-plan.md`.
- **Code changes:** one commit on branch `validate-cross-scope-and-accumulate` containing all source + test changes.
- **PR:** opened against `origin/main`.
