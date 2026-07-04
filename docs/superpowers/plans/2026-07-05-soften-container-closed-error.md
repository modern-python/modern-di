# Soften ContainerClosedError to a Self-Healing Deprecation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse of a closed container (`resolve` / `build_child_container`) emits a `ContainerClosedWarning` and self-reopens instead of raising `ContainerClosedError`, restoring pre-2.16 "close then resolve" behavior; the hard error returns as the default in 3.0.

**Architecture:** One private `Container._warn_and_reopen_if_closed()` helper replaces the four `if closed: raise ContainerClosedError(...)` sites. When called on a closed container it warns once and calls `self.open()`, then resolution proceeds. The two nested provider sites (`factory`, `context_provider`) call it on the `find_container(self.scope)` result, so a closed *ancestor* heals too. `ContainerClosedError` stays in the taxonomy (unraised until 3.0), covered by a direct unit test.

**Tech Stack:** Python 3.10+ (`enum.IntEnum`, `warnings` stdlib), pytest (`asyncio_mode=auto`), `just`, `uv`, `ruff` (`select=ALL`), `ty`.

**Spec:** [`docs/superpowers/specs/2026-07-05-soften-container-closed-error-design.md`](../specs/2026-07-05-soften-container-closed-error-design.md)

## Global Constraints

- **Zero runtime dependencies** — stdlib only (`warnings` is stdlib).
- **Line length 120**; `ruff` `select=["ALL"]` (minimal ignores); `ty` for typing. Use `ty: ignore`, never `type: ignore`.
- **All imports at module level**; annotate every function argument.
- **Cross-class access to a `_`-prefixed method needs `# noqa: SLF001`** (precedent: `modern_di/providers/alias.py:63`).
- **100% line coverage** on the gated run `just test-ci` (CI). Targeted `just test <path>` runs are ungated.
- The emitted warning is a `DeprecationWarning` subclass.
- Ships in **2.22.0** (backward-compatible). The hard `ContainerClosedError` default returns in **3.0** — wording in messages/docstrings/docs must say "modern-di 3.0", never a dated window.
- Resolution is sync-only; finalizers may be sync or async — do not touch `close_sync`/`close_async` semantics.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `modern_di/exceptions.py` | Exception/warning taxonomy | Add `ContainerClosedWarning`; note 3.0 on `ContainerClosedError` docstring |
| `modern_di/container.py` | Container lifecycle + resolution entry | Add `import warnings`; add `_warn_and_reopen_if_closed`; rewire 2 entry sites |
| `modern_di/providers/factory.py` | Factory resolution | Rewire the closed-check at `resolve` |
| `modern_di/providers/context_provider.py` | Context value lookup | Rewire the closed-check; drop now-unused `exceptions` import |
| `tests/test_container.py` | Container behavior tests | Flip entry + nested reuse tests to `pytest.warns`; add warn/heal, strict-opt-in, error-class unit tests |
| `tests/providers/test_singleton.py` | Factory/singleton tests | Flip 3 reuse-after-close sites; trim unused import |
| `tests/providers/test_context_provider.py` | Context provider tests | Flip the closed-owner test; trim unused import |
| `architecture/containers.md` | Truth home: container lifecycle | Promote: reuse warns + self-heals (3.0 restores raise) |
| `docs/providers/lifecycle.md`, `docs/providers/errors-and-exceptions.md`, `docs/integrations/writing-integrations.md` | User docs | Match new behavior |
| `planning/changes/2026-07-05.01-soften-container-closed-error/` | Change bundle (Full lane) | `design.md` + `plan.md` |
| `planning/releases/2.22.0.md` | Release notes draft | New file |

---

### Task 1: Warning type, helper, and container entry sites

**Files:**
- Modify: `modern_di/exceptions.py` (after `ContainerClosedError`, ~line 118)
- Modify: `modern_di/container.py` (imports; `build_child_container` ~98-99; `resolve_provider` ~138-139; add helper near `open()` ~254)
- Test: `tests/test_container.py`, `tests/providers/test_singleton.py`

**Interfaces:**
- Produces: `modern_di.exceptions.ContainerClosedWarning(DeprecationWarning)` and `Container._warn_and_reopen_if_closed(self) -> None` (warns once + `self.open()` when `self.closed`, else no-op). Task 2 consumes the helper.

- [ ] **Step 1: Write the failing warn-and-heal tests** in `tests/test_container.py`. First adjust imports: add `import warnings` to the stdlib block (after `import copy`), and add `ContainerClosedWarning` to the existing `from modern_di.exceptions import (...)` block (keep `ContainerClosedError` — the error-class test below uses it). Both are referenced by their bare imported names, matching this file's import style. Then add after `test_open_reopens_closed_container` (~line 414):

```python
def test_reuse_after_close_warns_and_reopens() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        resolved = container.resolve(Container)
    assert resolved is container
    assert container.closed is False


def test_build_child_after_close_warns_and_reopens() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        child = container.build_child_container(scope=Scope.REQUEST)
    assert container.closed is False
    assert child.scope is Scope.REQUEST


def test_reuse_warns_once_per_close_cycle() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        container.resolve(Container)
        container.resolve(Container)
    closed_warnings = [w for w in caught if issubclass(w.category, ContainerClosedWarning)]
    assert len(closed_warnings) == 1


def test_strict_opt_in_reuse_raises() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ContainerClosedWarning)
        with pytest.raises(ContainerClosedWarning):
            container.resolve(Container)


def test_container_closed_error_message_and_attr() -> None:
    err = ContainerClosedError(container_scope=Scope.APP)
    assert err.container_scope is Scope.APP
    assert "closed" in str(err)
    assert "Create a new container" in str(err)
```

- [ ] **Step 2: Run the new tests — expect failure**

  Run: `just test tests/test_container.py -k "reuse_after_close or build_child_after_close or reuse_warns_once or strict_opt_in or closed_error_message"`
  Expected: FAIL — `AttributeError`/`ImportError` for `ContainerClosedWarning` (not defined yet), and the resolve calls currently raise `ContainerClosedError`.

- [ ] **Step 3: Add `ContainerClosedWarning` and note 3.0 on the error** in `modern_di/exceptions.py`. Insert directly after the `ContainerClosedError` class (after line 118):

```python
class ContainerClosedWarning(DeprecationWarning):
    """Reuse of a closed container (resolve / build a child) — transitional.

    The reuse works today because the container self-reopens, but it will raise
    :class:`ContainerClosedError` in modern-di 3.0. Opt into strict behavior now
    by escalating this warning::

        warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)
    """
```

  Update the `ContainerClosedError` docstring (line 109) to:

```python
    """Operation attempted on a closed container. Attr: ``container_scope``. Raised in modern-di 3.0; until then reuse emits :class:`ContainerClosedWarning` and self-reopens."""
```

- [ ] **Step 4: Add `import warnings`** to `modern_di/container.py` stdlib imports (alphabetical: after `import typing`, line 3):

```python
import enum
import threading
import typing
import warnings
```

- [ ] **Step 5: Add the helper** in `modern_di/container.py`. Insert immediately after the `open()` method (after line 254, before `__enter__`):

```python
    def _warn_and_reopen_if_closed(self) -> None:
        """Transitional shim for reuse of a closed container.

        Emits :class:`~modern_di.exceptions.ContainerClosedWarning` and reopens
        (so pre-2.16 "close then resolve" code keeps working); modern-di 3.0
        will raise :class:`~modern_di.exceptions.ContainerClosedError` here
        instead. One warning per close→reuse transition, since it self-reopens.
        """
        if not self.closed:
            return
        warnings.warn(
            f"Container (scope {self.scope.name}) is closed; resolving from it or building a child "
            "is deprecated and will raise ContainerClosedError in modern-di 3.0. Re-enter the "
            "container with `with`/`async with`, or call `open()`, before reusing it.",
            exceptions.ContainerClosedWarning,
            stacklevel=2,
        )
        self.open()
```

- [ ] **Step 6: Rewire the two entry sites** in `modern_di/container.py`.

  In `build_child_container`, replace (lines 98-99):

```python
        if self.closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)
```

  with:

```python
        self._warn_and_reopen_if_closed()
```

  In `resolve_provider`, replace (lines 138-139):

```python
        if self.closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)
```

  with:

```python
        self._warn_and_reopen_if_closed()
```

- [ ] **Step 7: Run the new tests — expect pass**

  Run: `just test tests/test_container.py -k "reuse_after_close or build_child_after_close or reuse_warns_once or strict_opt_in or closed_error_message"`
  Expected: PASS (5 tests).

- [ ] **Step 8: Flip the existing entry-path reuse tests in `tests/test_container.py`.**

  `test_closed_container_refuses_resolve_and_child_building` → rename and rewrite:

```python
def test_closed_container_warns_and_reopens_on_resolve_and_child_building() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        container.resolve(Container)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        container.build_child_container(scope=Scope.REQUEST)
```

  `test_closed_container_async_path`:

```python
async def test_closed_container_async_path() -> None:
    container = Container(scope=Scope.APP)
    await container.close_async()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
```

  In `test_async_context_manager_reopens`, replace the `with pytest.raises(ContainerClosedError):` block with:

```python
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
```

  In `test_open_reopens_closed_container`, replace the `with pytest.raises(ContainerClosedError):` block with:

```python
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
```

- [ ] **Step 9: Flip the entry-path reuse tests in `tests/providers/test_singleton.py`.**

  Add `ContainerClosedWarning` to the import (line 9):

```python
from modern_di.exceptions import (
    AsyncFinalizerInSyncCloseError,
    ContainerClosedWarning,
    FinalizerError,
)
```

  Remove `ContainerClosedError` from that import (it becomes unused in this file). Then replace each of the three blocks:

  Around line 56:

```python
    with pytest.warns(ContainerClosedWarning):
        app_container.resolve_provider(LocalGroup.singleton)
```

  Around line 100:

```python
    with pytest.warns(ContainerClosedWarning):
        container.resolve(str)
```

  In `test_persistent_provider_survives_close_reopen_cycle` (around line 472), replace the `# resolving while closed raises` block:

```python
    # resolving while closed warns and self-reopens (transitional; 3.0 restores the raise)
    with pytest.warns(ContainerClosedWarning):
        container.resolve(_PersistentBroker)
```

- [ ] **Step 10: Run the touched test files**

  Run: `just test tests/test_container.py tests/providers/test_singleton.py`
  Expected: PASS (all).

- [ ] **Step 11: Lint**

  Run: `just lint`
  Expected: no errors (autofix clean; no unused-import warnings).

- [ ] **Step 12: Commit**

```bash
git add modern_di/exceptions.py modern_di/container.py tests/test_container.py tests/providers/test_singleton.py
git commit -m "feat: soften closed-container reuse to self-healing ContainerClosedWarning at entry sites"
```

---

### Task 2: Rewire the nested provider sites

**Files:**
- Modify: `modern_di/providers/factory.py` (`resolve`, ~243-246)
- Modify: `modern_di/providers/context_provider.py` (`fetch_context_value`, ~48-52; imports line 4)
- Test: `tests/test_container.py`, `tests/providers/test_context_provider.py`

**Interfaces:**
- Consumes: `Container._warn_and_reopen_if_closed()` from Task 1.

- [ ] **Step 1: Write the failing nested warn-and-heal tests.**

  In `tests/test_container.py`, rewrite `test_resolving_through_closed_parent_via_open_child_raises`:

```python
def test_resolving_through_closed_parent_via_open_child_warns_and_reopens() -> None:
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    child = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()
    with pytest.warns(ContainerClosedWarning):
        broker = child.resolve(_PersistentBroker)
    assert isinstance(broker, _PersistentBroker)
    assert app.closed is False
```

  In `tests/providers/test_context_provider.py`, rewrite `test_context_provider_through_closed_owning_container_raises`:

```python
def test_context_provider_through_closed_owning_container_warns_and_reopens() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app = Container(groups=[MyGroup], context={datetime.datetime: now})
    child = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert child.resolve_provider(MyGroup.context_provider) == now
    assert app.closed is False
```

  Update the import in `tests/providers/test_context_provider.py` (line 7) to drop `ContainerClosedError` (now unused there) and add `ContainerClosedWarning`:

```python
from modern_di.exceptions import ArgumentResolutionError, ContainerClosedWarning
```

- [ ] **Step 2: Run the new nested tests — expect failure**

  Run: `just test tests/test_container.py::test_resolving_through_closed_parent_via_open_child_warns_and_reopens tests/providers/test_context_provider.py::test_context_provider_through_closed_owning_container_warns_and_reopens`
  Expected: FAIL — the nested sites still raise `ContainerClosedError`, so `pytest.warns` sees an exception instead of a warning.

- [ ] **Step 3: Rewire the factory site** in `modern_di/providers/factory.py`. Replace (lines 245-246):

```python
        if container.closed:
            raise exceptions.ContainerClosedError(container_scope=container.scope)
```

  with:

```python
        container._warn_and_reopen_if_closed()  # noqa: SLF001
```

- [ ] **Step 4: Rewire the context-provider site** in `modern_di/providers/context_provider.py`. Replace (lines 50-51):

```python
        if container.closed:
            raise exceptions.ContainerClosedError(container_scope=container.scope)
```

  with:

```python
        container._warn_and_reopen_if_closed()  # noqa: SLF001
```

  This removes the only `exceptions.` use in the file — change the import (line 4) from:

```python
from modern_di import exceptions, types
```

  to:

```python
from modern_di import types
```

- [ ] **Step 5: Run the nested tests — expect pass**

  Run: `just test tests/test_container.py::test_resolving_through_closed_parent_via_open_child_warns_and_reopens tests/providers/test_context_provider.py::test_context_provider_through_closed_owning_container_warns_and_reopens`
  Expected: PASS (2 tests).

- [ ] **Step 6: Lint (catches SLF001 / unused-import mistakes)**

  Run: `just lint`
  Expected: no errors. If SLF001 fires, confirm the `# noqa: SLF001` is on the call line; if F401 fires on `exceptions`, confirm the import was trimmed in Step 4.

- [ ] **Step 7: Full gated run**

  Run: `just test-ci`
  Expected: PASS with **100% line coverage**. (The removed `raise` branches are gone; the helper's two branches and `ContainerClosedError.__init__` are covered by Task 1 tests.)

- [ ] **Step 8: Commit**

```bash
git add modern_di/providers/factory.py modern_di/providers/context_provider.py tests/test_container.py tests/providers/test_context_provider.py
git commit -m "feat: self-heal closed-ancestor reuse at factory and context-provider sites"
```

---

### Task 3: Docs, architecture promotion, release notes, and change bundle

**Files:**
- Modify: `architecture/containers.md`, `docs/providers/lifecycle.md`, `docs/providers/errors-and-exceptions.md`, `docs/integrations/writing-integrations.md`
- Create: `planning/changes/2026-07-05.01-soften-container-closed-error/design.md`, `.../plan.md`, `planning/releases/2.22.0.md`

One task: it carries no runtime code, and its gate is `just lint-ci` (which validates planning bundles) plus a consistency read. Do not split — a reviewer would accept/reject the doc set as a unit.

- [ ] **Step 1: Promote the truth home** — edit `architecture/containers.md` lifecycle section. Find the lines stating reuse raises `ContainerClosedError` (the "`closed = True` — always set … Subsequent calls to `build_child_container` or `resolve_provider` raise `ContainerClosedError`" bullet, ~line 97-98) and rewrite to describe the transitional behavior:

  > **`closed = True`** — always set in a `finally` block, even if finalizers raised. Until modern-di 3.0, a subsequent `resolve_provider` / `build_child_container` (or a nested provider resolving at a closed ancestor scope) emits a `ContainerClosedWarning` and **self-reopens** the container, then proceeds — preserving pre-2.16 "close then resolve" code. Escalate the warning (`warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)`) to opt into the strict behavior early. In 3.0 these paths raise `ContainerClosedError` instead.

  Keep the existing `open()` / context-manager reopen paragraphs; they are unchanged.

- [ ] **Step 2: Update `docs/providers/lifecycle.md`** (§ "Closing and reopening", lines ~112-124). Replace the "raises `ContainerClosedError`" sentence and the `-> raises ContainerClosedError` code comment with the warn+self-heal description, e.g.:

  Prose (line ~112):
  > While a container is closed, resolving a dependency — or building a child container — emits a `ContainerClosedWarning` and reopens the container so the call succeeds (transitional; modern-di 3.0 will raise `ContainerClosedError` instead — see [Errors and exceptions](errors-and-exceptions.md)).

  Code comment (line ~124):
  ```python
  # container.resolve(Settings)  -> warns (ContainerClosedWarning) and self-reopens
  ```

- [ ] **Step 3: Update `docs/providers/errors-and-exceptions.md`.** Add `ContainerClosedWarning` context to the `ContainerClosedError` bullet (lines ~63-65):

  > **`ContainerClosedError`** — raised in modern-di **3.0** when you resolve from, or build a child of, a closed container. Until then that reuse emits a **`ContainerClosedWarning`** (a `DeprecationWarning`) and the container self-reopens. Re-enter the `with` block or call `open()` to reuse it cleanly; escalate the warning with `warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)` to fail fast today.

  Leave the tree diagram's `ContainerClosedError` node (line ~22) as-is (it is still a real class).

- [ ] **Step 4: Update `docs/integrations/writing-integrations.md`** (lines ~154-158 and the checklist item ~348-349). Soften "raises `ContainerClosedError` if reused" to "emits a `ContainerClosedWarning` (and, in 3.0, raises `ContainerClosedError`) if reused without reopening", keeping the "reopen the root container on startup" guidance as the recommended practice.

- [ ] **Step 5: Create the change bundle** `planning/changes/2026-07-05.01-soften-container-closed-error/design.md`:

```markdown
---
summary: Reuse of a closed container warns (ContainerClosedWarning) and self-reopens instead of raising; hard ContainerClosedError returns in 3.0.
---

# Design: Soften closed-container reuse to a self-healing deprecation

## Summary

The hard `ContainerClosedError` added in 2.16.0 broke "close then resolve"
code (including maintainer projects) that relied on pre-2.16 lenient behavior.
Reuse of a closed container now emits `ContainerClosedWarning` and self-reopens
so the call succeeds; the error returns as the default in 3.0. Full brainstorm
spec: `docs/superpowers/specs/2026-07-05-soften-container-closed-error-design.md`.

## Motivation

`resolve_provider` / `build_child_container` and two nested provider paths
(`factory`, `context_provider`) started raising when `closed=True`. Downstream
lifecycles that close then reuse require invasive rewrites. Making the change
transitional removes that forced migration.

## Non-goals

- A `Container(strict_closed=...)` toggle — deferred; the `warnings` filter
  covers strictness for now.
- Changing `close_sync` / `close_async` / `open` semantics.

## Design

One private `Container._warn_and_reopen_if_closed()` replaces the four
`if closed: raise` sites; it warns once and calls `self.open()`. Nested sites
call it on the `find_container(self.scope)` result, healing a closed ancestor.
`ContainerClosedError` is retained (unraised until 3.0) and covered by a direct
unit test. New `ContainerClosedWarning(DeprecationWarning)` is filterable to an
error for strict opt-in.

## Testing

Reuse-after-close tests flip from `pytest.raises(ContainerClosedError)` to
`pytest.warns(ContainerClosedWarning)` + success assertions; added tests cover
one-warning-per-cycle, nested-ancestor heal, strict opt-in, and the retained
error class. `just test-ci` stays at 100% line coverage.

## Risk

Low. Behavior is strictly more permissive than 2.16–2.21; code that expected
the error can escalate the warning. Main risk is doc drift — mitigated by the
`architecture/containers.md` promotion in this PR.
```

- [ ] **Step 6: Create the bundle plan pointer** `planning/changes/2026-07-05.01-soften-container-closed-error/plan.md`:

```markdown
# soften-container-closed-error — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Ship the self-healing `ContainerClosedWarning` (2.22.0); restore the
hard error in 3.0.

**Spec:** [`design.md`](./design.md)

**Full task breakdown:** `docs/superpowers/plans/2026-07-05-soften-container-closed-error.md`

**Commit strategy:** Per-task commits (warning+entry sites · provider sites · docs).
```

- [ ] **Step 7: Create the release notes draft** `planning/releases/2.22.0.md`:

```markdown
# modern-di 2.22.0 — closed-container reuse is a deprecation, not a hard error

Reuse of a closed container no longer raises. `resolve` / `build_child_container`
(and nested providers resolving at a closed ancestor scope) now emit a
`ContainerClosedWarning` and self-reopen the container, restoring pre-2.16
"close then resolve" behavior. The hard `ContainerClosedError` returns as the
default in **3.0**.

## Fix

- **Closed-container reuse is transitional again.** The `ContainerClosedError`
  introduced in 2.16.0 (#202) was a breaking change for lifecycles that close
  then keep resolving. Reuse now warns (`exceptions.ContainerClosedWarning`, a
  `DeprecationWarning`) and self-reopens instead of raising. One warning fires
  per close→reuse transition.

## Deprecation

- Resolving from / building a child of a closed container is deprecated and will
  raise `ContainerClosedError` in modern-di 3.0. Wrap the container in
  `with` / `async with`, or call `open()`, before reuse. To fail fast today:
  `warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)`.

## Downstream

No action required to keep working. Integrations that reopen the root container
on startup are already on the recommended path.

## Internals

- 100% line coverage across supported Python versions retained.
```

  Note: the maintainer finalizes/renames this file at release time (releases are tag-driven and may batch other changes).

- [ ] **Step 8: Validate planning bundles and docs lint**

  Run: `just check-planning && just lint-ci`
  Expected: both PASS (bundle structure valid; no lint regressions — `docs/` is excluded from ruff, so this validates the bundle wiring).

- [ ] **Step 9: Consistency read** — grep the repo for any remaining stale claim that reuse "raises `ContainerClosedError`" unconditionally:

  Run: `grep -rn "raises \`ContainerClosedError\`\|raise ContainerClosedError\|-> raises ContainerClosedError" docs/ architecture/`
  Expected: only 3.0-qualified mentions remain (no unconditional "raises" claims outside the retained-class descriptions).

- [ ] **Step 10: Commit**

```bash
git add architecture/containers.md docs/providers/lifecycle.md docs/providers/errors-and-exceptions.md docs/integrations/writing-integrations.md planning/changes/2026-07-05.01-soften-container-closed-error planning/releases/2.22.0.md
git commit -m "docs: document self-healing ContainerClosedWarning; add change bundle and 2.22.0 notes"
```

---

## Self-Review

**Spec coverage:**
- §1 warning type → Task 1 Steps 3.
- §2 helper + four call sites → Task 1 (helper + 2 entry sites), Task 2 (2 provider sites).
- §3 reuse semantics unchanged → asserted via `is` / same-object checks (Task 1 async/persistent tests, Task 2 nested tests); no `open`/`close` edits.
- §4 `ContainerClosedError` retained + covered → Task 1 docstring edit + `test_container_closed_error_message_and_attr`.
- §5 tests (flip, one-warning, nested, strict opt-in, error unit) → Task 1 Steps 1/8/9, Task 2 Steps 1.
- §6 docs + planning → Task 3.

**Placeholder scan:** No TBD/TODO; every code step shows full code; every command has expected output.

**Type/name consistency:** `ContainerClosedWarning`, `_warn_and_reopen_if_closed`, `ContainerClosedError(container_scope=...)`, and test names are used identically across tasks. `# noqa: SLF001` appears at both cross-class call sites.

**Note on imported names:** Task 1 tests reference the bare imported `ContainerClosedWarning` / `ContainerClosedError` (added to each test file's `from modern_di.exceptions import ...` block), not an `exceptions.` prefix — matching each test file's existing import style.
