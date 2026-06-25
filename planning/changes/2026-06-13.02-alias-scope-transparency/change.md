---
date: 2026-06-13
slug: alias-scope-transparency
summary: Deprecate decorative `Alias(scope=...)`; `validate()` checks scope transitively via `effective_scope` (X-4). Plan-only; spec = the code-docs audit report.
spec: ../../../audits/2026-06-12-code-docs-audit-report.md
outcome: validate() now checks scope transitively via effective_scope through aliases (X-4); decorative Alias(scope=) deprecated; enforces_dependency_scope stopgap retired; shipped as 2.17.0 in PR #207.
---

# Alias Scope Transparency (X-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Container.validate()` check scope ordering *transitively through aliases* (fixing audit finding X-4) and deprecate the decorative `Alias(scope=...)` parameter, shipping as **2.17.0**.

**Architecture:** An `Alias` is a transparent redirect — at resolution it already delegates to its source, ignoring its own `scope`. We make validation match that model: add `AbstractProvider.effective_scope(container)` (default `self.scope`); `Alias` overrides it to return the scope of its terminal source (following alias chains). `validate()`'s scope-ordering check uses `effective_scope` on both sides of every edge, so a shallow caller depending *through* an alias on a deeper provider is now flagged. This subsumes and **retires** the `enforces_dependency_scope` stopgap added in 2.16.0. The decorative `scope=` constructor parameter is **deprecated** (accepted-but-warned, kept internally for display only; removal slated for 3.0).

**Tech Stack:** Python 3.10–3.14, zero runtime deps, `just` + `uv`, pytest (`asyncio_mode=auto`), ruff `select=["ALL"]`, `ty`. 100% line coverage gate via `just test-ci`.

**Run commands:** targeted runs `uv run --no-sync pytest <path> -q` (coverage no longer in addopts). Full gate `just lint-ci && just test-ci`. Plus the 3.14 cross-version check at the end (see Task 5).

**Behavior-change note:** after this, `validate()` will *newly raise* `ValidationFailedError(InvalidScopeDependencyError)` for graphs of the shape `Factory(shallow) → Alias → Factory(deeper)` that previously passed validation (and failed only at runtime with `ScopeNotInitializedError`). This is the intended fix; it's called out in the release notes as a behavior change.

**Reference:** audit finding X-4 in `planning/audits/2026-06-12-code-docs-audit-report.md`; deferred entry in `planning/deferred.md`; current caveat in `docs/providers/alias.md`.

---

### Task 1: `effective_scope` mechanism + transitive validate (fix X-4)

**Files:**
- Modify: `modern_di/providers/abstract.py` (remove `enforces_dependency_scope`, add `effective_scope`)
- Modify: `modern_di/providers/alias.py` (remove `enforces_dependency_scope`, add `effective_scope`)
- Modify: `modern_di/container.py` (`validate._visit` edge check)
- Modify: `modern_di/exceptions.py` (`InvalidScopeDependencyError` optional effective-scope override)
- Test: `tests/providers/test_alias.py`, `tests/test_container.py`

- [ ] **Step 1: Write the failing tests.**

Append to `tests/providers/test_alias.py` (module level; match existing imports — `providers`, `Container`, `Scope`, `Group`, `exceptions`, `pytest`):

```python
class _XfourDeep: ...


class _XfourIface: ...


class _XfourCaller:
    def __init__(self, dep: _XfourIface) -> None:  # APP-scoped caller depends THROUGH the alias
        self.dep = dep


class _XfourGroup(Group):
    deep = providers.Factory(scope=Scope.REQUEST, creator=_XfourDeep)
    iface = providers.Alias(source_type=_XfourDeep, bound_type=_XfourIface)
    caller = providers.Factory(scope=Scope.APP, creator=_XfourCaller)


def test_validate_flags_shallow_caller_depending_through_alias_on_deeper_source() -> None:
    # X-4: APP caller -> Alias -> REQUEST source. validate() must now catch the transitive mismatch.
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        Container(scope=Scope.APP, groups=[_XfourGroup], validate=True)
    assert any(isinstance(e, exceptions.InvalidScopeDependencyError) for e in exc_info.value.errors)
    # the message must name the EFFECTIVE (REQUEST) scope of what the alias points at, not the alias's own
    assert "REQUEST" in str(exc_info.value)


class _OkDeep: ...


class _OkIface: ...


class _OkCaller:
    def __init__(self, dep: _OkIface) -> None:
        self.dep = dep


class _OkGroup(Group):
    deep = providers.Factory(scope=Scope.REQUEST, creator=_OkDeep)
    iface = providers.Alias(source_type=_OkDeep, bound_type=_OkIface)
    caller = providers.Factory(scope=Scope.REQUEST, creator=_OkCaller)  # same scope as source -> legit


def test_validate_allows_same_scope_caller_through_alias() -> None:
    # REQUEST caller -> Alias -> REQUEST source is legitimate; validate must NOT flag it.
    Container(scope=Scope.APP, groups=[_OkGroup], validate=True)  # must not raise
```

- [ ] **Step 2: Run to verify they fail.**

Run: `uv run --no-sync pytest tests/providers/test_alias.py -k "shallow_caller_depending_through_alias or same_scope_caller_through_alias" -q`
Expected: `test_validate_flags_shallow_caller...` FAILS (no error raised today — the alias's decorative scope masks the REQUEST source); the `allows_same_scope` test PASSES already.

- [ ] **Step 3: Implement `effective_scope` on the base.**

In `modern_di/providers/abstract.py`: **delete** the line `enforces_dependency_scope: typing.ClassVar[bool] = True`. Add a method (after `iter_validation_issues`):

```python
    def effective_scope(self, container: "Container") -> enum.IntEnum:  # noqa: ARG002
        """Scope used for validate()'s scope-ordering check.

        Transparent redirects (Alias) override this to report the scope of what they
        ultimately resolve to, so callers are checked against the real target's scope.
        """
        return self.scope
```

- [ ] **Step 4: Implement `effective_scope` on `Alias` + drop the flag.**

In `modern_di/providers/alias.py`: **delete** the line `enforces_dependency_scope = False`. Add:

```python
    def effective_scope(self, container: "Container") -> enum.IntEnum:
        # Follow the alias chain to its terminal (non-alias) source and report that scope.
        seen: set[int] = set()
        provider: AbstractProvider[typing.Any] = self
        while isinstance(provider, Alias):
            if provider.provider_id in seen:
                return self.scope  # alias cycle — reported separately by validate()'s cycle check
            seen.add(provider.provider_id)
            try:
                provider = provider._find_source(container)  # noqa: SLF001
            except exceptions.AliasSourceNotRegisteredError:
                return self.scope  # dangling source — reported separately (B-5)
        return provider.scope
```

- [ ] **Step 5: Use `effective_scope` in `validate`.**

In `modern_di/container.py`, the `_visit` edge loop currently reads:

```python
            for dep_name, dep_provider in dependencies.items():
                if provider.enforces_dependency_scope and dep_provider.scope > provider.scope:
                    validation_errors.append(
                        exceptions.InvalidScopeDependencyError(
                            provider=provider,
                            parameter_name=dep_name,
                            dep_provider=dep_provider,
                        )
                    )
                _visit(dep_provider)
```

Replace with (compute effective scopes both sides; pass the effective dep scope to the error for an accurate message):

```python
            provider_scope = provider.effective_scope(self)
            for dep_name, dep_provider in dependencies.items():
                dep_scope = dep_provider.effective_scope(self)
                if dep_scope > provider_scope:
                    validation_errors.append(
                        exceptions.InvalidScopeDependencyError(
                            provider=provider,
                            parameter_name=dep_name,
                            dep_provider=dep_provider,
                            dep_scope=dep_scope,
                        )
                    )
                _visit(dep_provider)
```

- [ ] **Step 6: Extend `InvalidScopeDependencyError` with an effective-scope override.**

In `modern_di/exceptions.py`, `InvalidScopeDependencyError.__init__` currently formats `dep_scope=dep_provider.scope.name`. Add an optional `dep_scope` parameter so validate can supply the effective (transitive) scope:

```python
class InvalidScopeDependencyError(RegistrationError):
    __slots__ = ("dep_provider", "parameter_name", "provider")

    def __init__(
        self,
        *,
        provider: "AbstractProvider[typing.Any]",
        parameter_name: str,
        dep_provider: "AbstractProvider[typing.Any]",
        dep_scope: enum.IntEnum | None = None,
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
                dep_scope=(dep_scope or dep_provider.scope).name,
            )
        )
```

(`enum` is already imported in `exceptions.py`. The `__slots__` is unchanged — `dep_scope` is only used to format the message, not stored. Don't add it to slots.)

- [ ] **Step 7: Update the existing X-4-era test that referenced the old behavior.**

`tests/providers/test_alias.py` has `test_validate_does_not_flag_alias_whose_scope_is_shallower_than_source` (added by the 2.16.0 partial fix): a REQUEST `_DeepImpl`, an APP-default `_ShallowIface` alias, validated from an APP root with **no caller** of the alias. Under the new model this still passes (the alias→source edge is effective-REQUEST vs effective-REQUEST → no flag, and nothing depends on the alias). Keep it — but verify it still passes in Step 8; if its docstring/comment references `enforces_dependency_scope`, update the comment to mention `effective_scope`. Do NOT delete it.

- [ ] **Step 8: Run the new tests + full gate.**

Run: `uv run --no-sync pytest tests/providers/test_alias.py tests/test_container.py -q` → all pass (including the two new tests and the retained X-4-era test).
Then `just lint-ci && just test-ci 2>&1 | tail -3` → green, 100% coverage. Confirm no remaining reference to `enforces_dependency_scope`: `rtk proxy grep -rn "enforces_dependency_scope" modern_di/ tests/` → only any test you intentionally keep; there should be **zero** in `modern_di/`. If the `effective_scope` base method's `return self.scope` line or the Alias cycle/dangling fallbacks are uncovered, add targeted tests: an alias-of-alias chain (effective scope follows two hops) and a mutual-alias pair under `validate()` (exercises the `seen` cycle fallback).

- [ ] **Step 9: Commit.**

```bash
git add modern_di/providers/abstract.py modern_di/providers/alias.py modern_di/container.py modern_di/exceptions.py tests/providers/test_alias.py tests/test_container.py
git commit -m "validate(): check scope transitively through aliases via effective_scope; retire enforces_dependency_scope (X-4)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 2: Deprecate the `Alias(scope=...)` parameter

**Files:**
- Modify: `modern_di/providers/alias.py` (`__init__`)
- Test: `tests/providers/test_alias.py`

Context: `Alias.scope` never affects resolution (the source's scope governs) and, post-Task-1, never affects validation either (effective scope is used). The parameter is purely decorative and misleading, so deprecate it. Keep storing an internal scope (default `Scope.APP`) only so the cosmetic readers (`__repr__`, `_resolution_step`, registry suggestions) keep working without a base-class change. Removal slated for 3.0.

- [ ] **Step 1: Write the failing tests** (append to `tests/providers/test_alias.py`):

```python
class _DepSrc: ...


def test_alias_scope_parameter_is_deprecated() -> None:
    with pytest.warns(DeprecationWarning, match="scope"):
        providers.Alias(source_type=_DepSrc, bound_type=object, scope=Scope.REQUEST)


def test_alias_without_scope_emits_no_deprecation_warning() -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning becomes an error
        alias = providers.Alias(source_type=_DepSrc, bound_type=object)
    assert alias is not None
```

- [ ] **Step 2: Run to verify they fail.**

Run: `uv run --no-sync pytest tests/providers/test_alias.py -k "scope_parameter_is_deprecated or without_scope_emits_no" -q`
Expected: `is_deprecated` FAILS (no warning emitted today); `without_scope_emits_no` PASSES.

- [ ] **Step 3: Implement the deprecation.**

In `modern_di/providers/alias.py`, add `import warnings` at the top with the other stdlib imports. Change `__init__` to use a sentinel so an explicit `scope=` can be detected:

```python
    def __init__(
        self,
        *,
        source_type: type[types.T_co],
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: type | None | types.UnsetType = types.UNSET,
    ) -> None:
        if not isinstance(scope, types.UnsetType):
            warnings.warn(
                "The `scope` parameter of Alias is deprecated and ignored: an alias's effective "
                "scope is derived from its source. It will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
            stored_scope: enum.IntEnum = scope
        else:
            stored_scope = Scope.APP
        super().__init__(
            scope=stored_scope, bound_type=source_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        self._source_type = source_type
```

(`types.UnsetType` / `types.UNSET` are already the sentinel used elsewhere in the codebase — confirm by reading `modern_di/types.py`. `Scope` is already imported in alias.py.)

- [ ] **Step 4: Update the existing repr test.**

`tests/providers/test_alias.py:123-125` constructs `providers.Alias(..., scope=Scope.REQUEST)` and asserts the repr includes `scope=<Scope.REQUEST: 3>`. That call now emits a `DeprecationWarning`. Wrap the construction in `with pytest.warns(DeprecationWarning):` and keep the repr assertion (the passed scope is still stored for display, so the repr is unchanged). Read the test first and adjust minimally.

- [ ] **Step 5: Run + full gate.**

Run: `uv run --no-sync pytest tests/providers/test_alias.py -q` → all pass.
Then `just lint-ci && just test-ci 2>&1 | tail -3` → green, 100% coverage. (The deprecation `warnings.warn` branch is covered by the new test; the no-warning branch by the rest of the alias suite.)

- [ ] **Step 6: Commit.**

```bash
git add modern_di/providers/alias.py tests/providers/test_alias.py
git commit -m "Deprecate the decorative Alias(scope=...) parameter (derived from source; removal in 3.0)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3: Documentation

**Files:**
- Modify: `docs/providers/alias.md`
- Modify: `docs/providers/container.md` (the G-10 "Advanced" subsection)

- [ ] **Step 1: Update `docs/providers/alias.md`.** Two edits:
  - The `### scope` section (around lines 17-19) currently says scope is decorative and "setting it to match the source's scope is a reasonable convention." Replace with: the `scope` parameter is **deprecated** and ignored — an alias's effective scope is derived from its source; passing `scope=` emits a `DeprecationWarning` and the parameter will be removed in 3.0.
  - The `!!! caution "Alias scope is not enforced through validate()"` admonition (around lines 105-109) is now **false** — replace it with a note that `Container.validate()` **does** check scope transitively through aliases: a shallow-scoped caller depending through an alias on a deeper-scoped source is flagged with `InvalidScopeDependencyError` at validation time (no longer only at runtime).
  - Verify any runnable example on the page still executes: re-run the page's stitched code blocks (`/tmp/alias_doc.py`) and confirm exit 0. If a block passed `scope=` to `Alias`, drop it (and note the deprecation).

- [ ] **Step 2: Update `docs/providers/container.md` Advanced subsection (G-10).** It documents subclassing `AbstractProvider` and mentions setting `enforces_dependency_scope = False` for decorative-scope providers. That flag no longer exists. Replace that bullet with: a transparent/redirect provider should **override `effective_scope(container)`** to report the scope of what it ultimately resolves to (as `Alias` does), so `validate()` checks callers against the real target scope. Keep the rest of the advanced surface list intact.

- [ ] **Step 3: `just lint-ci`** (eof-fixer/ruff touch markdown) → clean. Confirm the alias doc example runs (`/tmp/alias_doc.py` exit 0).

- [ ] **Step 4: Commit.**

```bash
git add docs/providers/alias.md docs/providers/container.md
git commit -m "Docs: alias scope deprecated + validate() now transitive; document effective_scope override (X-4)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4: Release notes + close the deferred item

**Files:**
- Create: `planning/releases/2.17.0.md`
- Modify: `planning/deferred.md`

- [ ] **Step 1: Write `planning/releases/2.17.0.md`** in the established format (see `planning/releases/2.16.1.md` / `2.16.0.md`):

```markdown
# modern-di 2.17.0 — Alias scope transparency

Mostly additive. **One behavior change in `Container.validate()`** is called out below.

## Fix

- **`validate()` now checks scope ordering transitively through aliases (X-4).** An alias is a transparent redirect — at resolution its source's scope governs where the instance lives. Validation now matches that: a shallow-scoped caller depending *through* an alias on a deeper-scoped source is flagged with `InvalidScopeDependencyError` at validation time, instead of passing `validate()` and failing only at runtime with `ScopeNotInitializedError`. Implemented via a new `AbstractProvider.effective_scope(container)` hook (default `self.scope`; `Alias` follows its source chain). This replaces the internal `enforces_dependency_scope` flag introduced in 2.16.0.

## Behavior changes

- **`validate()` may newly raise** `ValidationFailedError(InvalidScopeDependencyError)` for graphs of the shape `Factory(shallow) → Alias → Factory(deeper)` that previously passed validation. These graphs were already broken (they raised `ScopeNotInitializedError` at resolve time); `validate()` now surfaces them up front. No change for correctly-scoped graphs.

## Deprecations

- **`Alias(scope=...)` is deprecated.** The parameter never affected resolution and (as of this release) no longer affects validation — an alias's effective scope is derived from its source. Passing `scope=` emits a `DeprecationWarning`; the parameter will be removed in 3.0.

## Internals

- Removed the `AbstractProvider.enforces_dependency_scope` ClassVar (superseded by `effective_scope`). Custom transparent providers should override `effective_scope(container)` instead.
- 100% line coverage maintained across Python 3.10–3.14.

## References

- Audit finding X-4: [`planning/audits/2026-06-12-code-docs-audit-report.md`](../audits/2026-06-12-code-docs-audit-report.md)
- Plan: [`planning/plans/2026-06-13-alias-scope-transparency.md`](../plans/2026-06-13-alias-scope-transparency.md)
```

- [ ] **Step 2: Remove the X-4 item from `planning/deferred.md`.** It is now the only item; after removing it, the file's body has no remaining items. Replace the items section with a single line: `_No deferred items at present._` (keep the title + intro paragraph).

- [ ] **Step 3: `just lint-ci`** → clean.

- [ ] **Step 4: Commit.**

```bash
git add planning/releases/2.17.0.md planning/deferred.md
git commit -m "Release notes for 2.17.0; clear the X-4 deferred item" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 5: Final verification

- [ ] **Step 1: Full gate.** `just lint-ci && just test-ci 2>&1 | tail -3` → green, 100% coverage. Report the test count.

- [ ] **Step 2: Cross-version (3.14) check** (the standing lesson — verify before shipping):

```bash
uv run --python 3.14 --with typing_extensions --with pytest-cov --with pytest-asyncio --with pytest-benchmark --with pytest-repeat pytest tests/ --cov=. --cov-report= --cov-fail-under=100 -p no:cacheprovider -q 2>&1 | tail -3
```
→ green at 100%. **Then restore the venv** (the 3.14 run repoints `.venv`): `uv venv --python 3.13 --clear && uv sync --all-extras --frozen --group lint`, and re-confirm `just test-ci` is green.

- [ ] **Step 3: Adversarial spot-check** (manual, no commit): write `/tmp/x4_check.py` covering — (a) `Factory(APP) → Alias → Factory(REQUEST)` → `validate()` raises naming REQUEST; (b) `Factory(REQUEST) → Alias → Factory(REQUEST)` → passes; (c) alias-of-alias to a deep source → effective scope follows the chain and flags a shallow caller; (d) `Alias(scope=...)` emits `DeprecationWarning` but still resolves correctly; (e) a genuine same-scope graph validates clean. Run with `uv run --no-sync python /tmp/x4_check.py`; all assertions pass.

- [ ] **Step 4: Hand off.** This branch is PR-ready. Publishing 2.17.0 (tag + GitHub release → PyPI) is outward-facing and happens after merge on explicit go-ahead, following the established release procedure (tag the merge commit, `gh release create 2.17.0 --notes-file planning/releases/2.17.0.md`, verify the publish run + PyPI).
