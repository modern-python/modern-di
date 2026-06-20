---
status: shipped
date: 2026-06-05
slug: singleton-rlock
spec: design.md
pr: null
---

# Singleton RLock Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a TDD-driven one-line fix that changes `Container`'s per-container lock from `threading.Lock` to `threading.RLock`, eliminating the deadlock the audit surfaced when a creator legitimately re-enters `container.resolve_provider(...)`.

**Architecture:** TDD red→green. Write the regression test first against current `main`, watch it time out (proving the deadlock exists), apply the one-line fix in `modern_di/container.py:39`, watch it pass. Test exercises the documented `Container`-typed-parameter auto-injection pattern, so it fails for the exact reason a real user would hit it.

**Tech Stack:** Python (the library); `pytest` (test runner); `ThreadPoolExecutor` + `Future.result(timeout=...)` to make the deadlock surface as a `TimeoutError` instead of hanging CI; `just lint` / `uv run ruff` / `uv run ty` for hygiene; `gh` for the PR.

---

## File structure

**Modified by this plan:**
- `modern_di/container.py:39` — one-line change (`Lock` → `RLock`).
- `tests/providers/test_singleton.py` — one new test function added near the existing `test_singleton_threading_concurrency` at line 233.

**Created:** nothing.

**No new imports needed.** The test file already has `ThreadPoolExecutor`, `Container`, `Group`, `providers`.

**Spec reference:** `planning/specs/2026-06-05-singleton-rlock-design.md`. Read it before starting.

---

## Background — quick context the engineer needs

The bug: `Container.lock = threading.Lock()` at `modern_di/container.py:39`. `Factory.resolve` (at `modern_di/providers/factory.py:156-168`) acquires that lock around `self._creator(**resolved_kwargs)`. When the creator's `__init__` accepts `container: Container` (an auto-injected reference, documented at `docs/providers/container.md:14-46`) and calls `container.resolve(OtherType)`, the nested call tries to acquire the same non-reentrant lock on the same thread and hangs.

`threading.RLock` is a drop-in replacement: same `.acquire()` / `.release()` API; allows the same thread to re-enter; other threads still block. The fix is the construction line only — the consumer at `factory.py:156-168` does not change.

Why TDD here: the bug currently masks itself (hang, not exception). Writing the test first against unfixed `main` proves the bug is real and demonstrates the failure mode; running it again after the fix proves the change does what it claims.

---

## Task 1: Implement the fix via TDD

**Files:**
- Modify: `modern_di/container.py:39`
- Modify: `tests/providers/test_singleton.py` (append a new test function)

- [ ] **Step 1: Create the feature branch**

```bash
git -C /Users/kevinsmith/src/pypi/modern-di switch -c use-rlock-for-reentrant-resolution
git -C /Users/kevinsmith/src/pypi/modern-di status
```

Expected: branch switched to `use-rlock-for-reentrant-resolution`, working tree clean.

- [ ] **Step 2: Write the failing regression test**

Append this function to `tests/providers/test_singleton.py`. Place it immediately after the existing `test_singleton_threading_concurrency` function (which ends around line 260). All needed names (`ThreadPoolExecutor`, `Container`, `Group`, `providers`) are already imported at the top of the file (verified — `from concurrent.futures import ThreadPoolExecutor, as_completed` is at line 4; `Container, Group, providers` at line 8). No new imports.

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

- [ ] **Step 3: Run the new test and confirm it times out**

```bash
uv run pytest tests/providers/test_singleton.py::test_singleton_resolution_is_reentrant -v
```

Expected: **FAIL** after approximately 5 seconds with `concurrent.futures._base.TimeoutError` (or `TimeoutError` on newer Python). This is the bug surfacing — the deadlock holds, `future.result(timeout=5)` raises. If the test passes here, the bug is not present in the way the audit described; STOP and investigate before applying a fix.

(If pytest hangs longer than ~15 seconds, the timeout is malfunctioning — kill it with `Ctrl+C` and verify the test code was copied exactly.)

- [ ] **Step 4: Apply the one-line fix**

Edit `modern_di/container.py`, line 39. Current line:

```python
        self.lock = threading.Lock() if use_lock else None
```

Change to:

```python
        self.lock = threading.RLock() if use_lock else None
```

That is the entire production-code diff. No other line in the file changes. Do not edit `factory.py`, `__slots__`, or any type annotation — `lock` has no explicit annotation and the consumer at `factory.py:156-168` uses only `.acquire()` / `.release()` which both `Lock` and `RLock` expose identically.

- [ ] **Step 5: Re-run the new test and confirm it passes**

```bash
uv run pytest tests/providers/test_singleton.py::test_singleton_resolution_is_reentrant -v
```

Expected: **PASS** in under 1 second. If it still times out, the fix did not land — re-check line 39 of `modern_di/container.py`.

- [ ] **Step 6: Run the full test suite to confirm no regression**

```bash
uv run pytest
```

Expected: all tests pass, including the pre-existing `test_singleton_threading_concurrency` at `tests/providers/test_singleton.py:233`. If any test fails, STOP and investigate before committing — the lock change must not break thread-safety guarantees that other tests depend on.

- [ ] **Step 7: Lint and type-check**

```bash
just lint-ci
```

(If `just` is not available, the equivalent direct commands are:
```bash
uv run ruff format --check . && uv run ruff check . && uv run ty check
```
Per the project's `Justfile`, `just lint-ci` runs the same checks without auto-fixing.)

Expected: clean. No formatting / lint / type errors.

If `ruff` flags formatting on the new test, run `uv run ruff format .` to fix and re-run `just lint-ci`.

- [ ] **Step 8: Commit**

```bash
git -C /Users/kevinsmith/src/pypi/modern-di add modern_di/container.py tests/providers/test_singleton.py
git -C /Users/kevinsmith/src/pypi/modern-di commit -m "Use threading.RLock so singleton resolution is re-entrant"
git -C /Users/kevinsmith/src/pypi/modern-di log --oneline -1
```

Expected: one commit with the exact subject `Use threading.RLock so singleton resolution is re-entrant`, touching exactly the two files. No body required — the subject is sufficient and matches the project's existing style (see `git log --oneline -10` for precedent).

---

## Task 2: Push and open the PR

**Files:** none modified locally; this task ships the branch.

- [ ] **Step 1: Push the branch**

```bash
git -C /Users/kevinsmith/src/pypi/modern-di push -u origin use-rlock-for-reentrant-resolution
```

Expected: branch created on `origin`, tracking set.

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "Use threading.RLock so singleton resolution is re-entrant" --body "$(cat <<'EOF'
## Summary
- `Container.lock` was a plain `threading.Lock`; `Factory.resolve` acquires it around the creator call. When a creator legitimately re-enters `container.resolve_provider(other_singleton)` on the same container — the documented `Container`-typed-parameter auto-injection pattern — the nested call deadlocks on the non-reentrant lock.
- This change swaps the construction at `modern_di/container.py:39` to `threading.RLock`. Same `.acquire()` / `.release()` API; same thread re-enters; other threads still block.
- One-line production diff; one new regression test in `tests/providers/test_singleton.py` exercising the documented re-entry pattern with a 5-second timeout that surfaces the deadlock as a `TimeoutError` instead of hanging CI.

Surfaced by the 2026-06-05 bug-hunt audit (`planning/audits/2026-06-05-bug-hunt-audit-report.md`, must-fix-now #1). Design: `planning/specs/2026-06-05-singleton-rlock-design.md`.

## Test plan
- [x] New test `test_singleton_resolution_is_reentrant` passes locally (<1s).
- [x] New test confirmed to fail on pre-fix `main` (~5s timeout) — TDD red→green.
- [x] Full suite (`uv run pytest`) green.
- [x] `just lint-ci` green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: `gh` returns the PR URL. Report the URL when done.

- [ ] **Step 3: Confirm CI is running**

```bash
gh pr checks --watch
```

Expected: CI checks kick off; either watch them complete or stop here and let CI run in the background. If a check fails, investigate the failure and decide whether to fix-on-branch or close-and-restart.

---

## Self-review

**Spec coverage check:**

- Goal (one-line fix + one TDD test, single PR) — covered by Task 1.
- Success criteria #1 (test fails on `main` before fix) — Task 1 Step 3.
- Success criteria #2 (test passes after fix in <1s) — Task 1 Step 5.
- Success criteria #3 (existing suite still green) — Task 1 Step 6.
- Success criteria #4 (`ruff format && ruff check && ty check` clean) — Task 1 Step 7 (`just lint-ci` is the project's wrapper).
- The change (one-line edit at `container.py:39`) — Task 1 Step 4, exact diff shown.
- Test design (exact code, `ThreadPoolExecutor`, `future.result(timeout=5)`) — Task 1 Step 2, verbatim.
- Branch name (`use-rlock-for-reentrant-resolution`) — Task 1 Step 1 and Task 2 Step 1.
- Commit message (`Use threading.RLock so singleton resolution is re-entrant`) — Task 1 Step 8.
- PR (via `gh pr create`, body cites audit report and spec) — Task 2 Step 2.
- Non-goals (no `factory.py` edit, no per-CacheItem locks, no doc rewrite) — reinforced in Task 1 Step 4 instructions.

**Placeholder scan:** none. Every code block is the actual code; every command is the actual command; no "TBD" / "TODO" / "similar to above".

**Type / name consistency:** all references — `threading.RLock`, `Container`, `Group`, `providers.Factory`, `providers.CacheSettings`, `ThreadPoolExecutor`, `future.result(timeout=5)`, branch name, commit subject, PR title — match between tasks. No drift.

**Sequencing sanity:** TDD discipline preserved — test before fix; both individual-test and full-suite runs required; lint/type before commit; commit before push; push before PR; PR before watching CI. No reordering possible without breaking the discipline the spec demanded.
