---
status: shipped
date: 2026-06-05
slug: singleton-rlock
summary: RLock-guarded singleton creation to eliminate re-entrant deadlock; shipped in 2.15.0.
supersedes: null
superseded_by: null
outcome: RLock guards singleton creation; shipped in 2.15.0.
---

# Singleton Re-Entrant Lock Fix — Design

**Date:** 2026-06-05
**Status:** Draft, pending user approval
**Source:** `planning/audits/2026-06-05-bug-hunt-audit-report.md`, `must-fix-now` finding "Singleton lock is non-reentrant — nested singleton resolution deadlocks the calling thread"

## Goal

Eliminate the documented re-entrant-resolution deadlock by changing the per-`Container` lock from `threading.Lock` to `threading.RLock`. Land it as one focused PR matching the project's existing conventions.

## Background

The audit's first `must-fix-now` finding (`planning/audits/2026-06-05-bug-hunt-audit-report.md`) documents that `Container.lock` is a plain `threading.Lock`, acquired in `Factory.resolve` (`modern_di/providers/factory.py:156-168`) around `self._creator(**resolved_kwargs)`. When a creator legitimately re-enters `container.resolve_provider(other_singleton)` on the same container — a pattern documented at `docs/providers/container.md:14-46` via the auto-registered `container_provider` — the nested call tries to acquire the same non-reentrant lock on the same thread and deadlocks permanently. All three audit verifiers confirmed (3/3), including direct execution of the repro that hangs.

Affected lines:

- `modern_di/container.py:39` — lock construction (single edit site).
- `modern_di/providers/factory.py:156-168` — lock consumer (unchanged by this PR; `RLock` exposes the same `.acquire()/.release()` API).

The documented `Container`-typed-parameter injection pattern is the canonical way users wire access to the container from inside a creator. The bug breaks the canonical pattern. The fix restores it.

## Scope

### In scope

- One-line change at `modern_di/container.py:39`.
- One new regression test in `tests/providers/test_singleton.py`.
- One commit, one feature branch, one PR.

### Non-goals

- **Per-`CacheItem` locks** (the audit's `wont-fix` discussion of head-of-line blocking). Different concern, different PR.
- **`factory.py` consumer changes.** Both `Lock` and `RLock` expose `.acquire()/.release()` identically; no edit needed.
- **Documentation rewrites.** `CLAUDE.md` describes the lock as a "thread-safety primitive" — still accurate; the fix removes a deadlock without changing the conceptual model.
- **`use_lock=False` propagation.** The audit's "build_child_container drops use_lock=False" UX finding is a separate item.
- **Performance benchmarking.** Out of scope here; can be a follow-up if perf becomes a concern.

## Success criteria

1. The new regression test, written first against current `main`, times out (demonstrates the bug).
2. With the one-line fix applied, the new regression test passes in under 1 second.
3. The pre-existing `test_singleton_threading_concurrency` at `tests/providers/test_singleton.py:233` and the rest of the suite continue to pass.
4. `ruff format && ruff check && ty check` clean.

## The change

Single-line edit in `modern_di/container.py:39`:

```python
# before
self.lock = threading.Lock() if use_lock else None
# after
self.lock = threading.RLock() if use_lock else None
```

The attribute is implicit-typed (no explicit annotation; `__slots__` at line 22 lists `"lock"` without a type). `ty` infers `threading.RLock | None` after the change. No annotation update required.

## Test design

New regression test, placed near the existing `test_singleton_threading_concurrency` in `tests/providers/test_singleton.py`:

```python
def test_singleton_resolution_is_reentrant() -> None:
    class Inner:
        pass

    class Outer:
        def __init__(self, container: Container) -> None:
            self.inner = container.resolve(Inner)

    class ReentrantGroup(Group):
        inner = providers.Factory(creator=Inner, cache_settings=providers.CacheSettings())
        outer = providers.Factory(creator=Outer, cache_settings=providers.CacheSettings())

    container = Container(groups=[ReentrantGroup])

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(container.resolve, Outer)
        result = future.result(timeout=5)

    assert isinstance(result, Outer)
    assert isinstance(result.inner, Inner)
```

**Design notes:**

- **Mirrors the existing concurrency-test pattern** (`ThreadPoolExecutor` plus `future.result`). `ThreadPoolExecutor` is already imported in the file.
- **Exercises the documented auto-injection pattern.** `Outer.__init__` takes `container: Container`, the canonical way to access the container from inside a creator. The test fails for the reason a real user would hit it, not a contrived scenario.
- **`future.result(timeout=5)`** raises `TimeoutError` if the deadlock returns. The test fails loudly within 5 seconds rather than hanging CI forever. The leaked worker thread is irrelevant once pytest tears down the process.
- **Both providers use `cache_settings=CacheSettings()`** because the lock is only acquired on cached / singleton resolution paths (`factory.py:156`). The bug does not manifest for non-cached factories.

## Branch, commit, PR conventions

Match patterns visible in `git log --oneline`:

- **Branch name:** `use-rlock-for-reentrant-resolution`.
- **Commit message:** `Use threading.RLock so singleton resolution is re-entrant`. Imperative present-tense, no conventional-commits prefix. Mirrors recent style (`Use UNSET sentinel for CacheItem.cache so None becomes a valid cached value`).
- **PR:** `gh pr create` targeting `main`. Title same as the commit. Body cites the audit report path, the deadlock repro, the one-line fix, and notes that the fix is TDD-driven (test written first against `main`, observed timeout, then fix applied).

## Sequencing

1. Branch off current `main`.
2. Write the failing test. Do not commit yet.
3. `uv run pytest tests/providers/test_singleton.py::test_singleton_resolution_is_reentrant -v` — confirm the test times out after 5 seconds.
4. Apply the one-line fix in `modern_di/container.py:39`.
5. `uv run pytest tests/providers/test_singleton.py::test_singleton_resolution_is_reentrant -v` — confirm the test passes in <1s.
6. `uv run pytest` (full suite) — confirm no regression.
7. `uv run ruff format . && uv run ruff check . --fix && uv run ty check` — clean.
8. Single commit: test + fix together.
9. `git push -u origin use-rlock-for-reentrant-resolution`.
10. `gh pr create` with the audit-cited body.

## Risks

- **Marginal `RLock` overhead.** One additional branch in `_thread.RLock.acquire` versus `Lock`. For a DI library that locks once per cached resolution, the difference is unmeasurable. Out of scope to benchmark; can be revisited if perf shows up as a concern.
- **Future maintainer reading the diff might ask "why `RLock`?"** The commit message, test name, and test body make this obvious — no inline code comment needed.

## Deliverables

- **This spec:** `planning/specs/2026-06-05-singleton-rlock-design.md`.
- **Implementation plan (next phase, via writing-plans):** `planning/plans/2026-06-05-singleton-rlock-plan.md`.
- **Code changes:** one commit on branch `use-rlock-for-reentrant-resolution` containing the new test plus the one-line fix.
- **PR:** opened against `origin/main`.
