# scope-error-breadcrumbs — implementation plan

**Goal:** Runtime scope errors render the full dependency chain naming both ends.
**Spec:** [`design.md`](./design.md)
**Branch:** `feat/scope-error-breadcrumbs`
**Commit strategy:** per-task commits.

### Task 1: Mixin + widened prepend sites (TDD)

**Files:** `modern_di/exceptions.py`, `modern_di/providers/factory.py`,
`modern_di/providers/alias.py`; tests in `tests/test_dependency_path.py`.

- [ ] Failing tests first (design's Testing list: captive repro asserting both
      names + `caused by:` scope message; byte-identical top-level message;
      `except ContainerError` compatibility; alias step).
- [ ] RED run, then implement: extract `DependencyPathMixin` (slots
      `_base_message`, `dependency_path`; `prepend_step`; chain `__str__`;
      cooperative `__init__`); rebase `ResolutionError` and the two scope
      errors onto it; widen `factory.py:253` and `alias.py:69-74` excepts to
      the explicit 3-tuple; wrap `factory.py:244`'s `find_container` to
      prepend the failing factory's own step.
- [ ] GREEN: targeted file, then full suite; `just test-ci` at 100% (mixin
      lines all covered), `just lint-ci`.
- [ ] Commit: `feat: breadcrumb dependency chains on runtime scope errors (ERR-3)`

### Task 2: Docs promotion

**Files:** `architecture/resolution.md` (breadcrumb section: now also scope
errors), `architecture/scopes.md` (error-shape note), 
`docs/providers/errors-and-exceptions.md` (scope-error entries mention the
chain); verify `just docs-build`.

- [ ] Commit: `docs: promote scope-error breadcrumbs into architecture/`
