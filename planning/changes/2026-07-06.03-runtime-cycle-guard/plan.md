# runtime-cycle-guard — implementation plan

**Goal:** Unvalidated cycles fail as diagnosed `CircularDependencyError`, never raw `RecursionError`.
**Spec:** [`design.md`](./design.md)
**Branch:** `feat/runtime-cycle-guard`
**Commit strategy:** per-task commits.

### Task 1: Finder + guard (TDD)

**Files:** `modern_di/container.py`; tests in a new
`tests/test_runtime_cycle_guard.py`.

- [ ] Failing tests first (design's Testing list: simple cycle, deep-chain
      cycle with breadcrumbs, self-recursing creator passthrough, __cause__
      chaining).
- [ ] RED, then implement: module-private iterative finder (explicit stack,
      `get_dependencies`, `display_name` names, first name repeated — same
      shape as container.py:191-194); `try/except RecursionError` around
      `provider.resolve(self)` in `resolve_provider`.
- [ ] GREEN; full suite; `just test-ci` (100% — both handler branches
      covered), `just lint-ci`.
- [ ] Commit: `feat: runtime cycle guard — CircularDependencyError instead of raw RecursionError (ERR-1)`

### Task 2: Docs promotion

**Files:** `architecture/validation.md`, `docs/providers/errors-and-exceptions.md`,
`docs/troubleshooting/circular-dependency.md`; `just docs-build`.

- [ ] Commit: `docs: promote the runtime cycle guard into architecture/ and troubleshooting`
